"""`TableSession`: one private table above one `HoldemGame` (ADR 0005 §6-11, ADR 0006).

The session owns its members (each a `UserId` and a table-visible `DisplayName`, with a seat), the host, pending
intents, the departed users, the shared revision and its current engine generation (one `Table` and one `HoldemGame`,
never handed out). It decides nothing about poker: stacks, participation status, turn, legality, pots and cards are
read from the engine, and the engine's errors decide a rejection.

Every state-changing command takes `expected_revision` and is rejected on a mismatch before anything else. Every
rejection is decided before anything changes: the checks run first, and the only engine call that can reject is the
command's first change and is atomic in the engine. A rejection therefore leaves the session, the engine and the
revision unchanged. The engine outcomes a resume expects (too few players, no `READY` player with chips) are handled
application outcomes - waiting or an engine-generation reset - not command rejections. An unexpected or unmapped
exception is a defect: it propagates without rollback, and the in-memory session must then be treated as failed. This
is narrow atomicity, consistent with the engine's. Each successful shared change is a `Transition`: it increments the
revision once and captures every member's view. Private intents change no revision. A pre-action selection is a private
intent that every shared transition reconciles before its views are captured (`_reconcile_pre_actions`); a selection
whose owner's turn has arrived is consumed there and executed as the next transition of the same command.
"""

from collections.abc import Callable
from dataclasses import dataclass
from types import MappingProxyType

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.app.results import Accepted, CommandResult, Rejected, RejectionCode, Transition, TransitionCause
from go_poker.app.views import SessionSeatView, TablePhase, TableSettings, TableView, YouView
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, NotPlayersTurnError
from go_poker.game.betting.legal_actions import LegalActions, call_obligation, legal_actions
from go_poker.game.game_lifecycle import ButtonChooser, GameNotStartedError
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import HandAlreadySettledError
from go_poker.game.position import InvalidPlayerCount
from go_poker.game.seat import SeatOccupiedError
from go_poker.game.showdown import NotShowdownTurnError, ShowdownAction
from go_poker.game.street import Street
from go_poker.game.table import InvalidSeatNumber, Table
from go_poker.game.variants.texas_holdem.game import HoldemGame
from go_poker.game.variants.texas_holdem.hand_flow import current_actor
from go_poker.game.variants.texas_holdem.showdown import ShowdownNotStartedError
from go_poker.game.variants.texas_holdem.view import holdem_view
from go_poker.game.visibility import viewer_participant_seat


@dataclass(frozen=True)
class _Selection:
    """A stored pre-action selection: the selected intent, and the hand and street it was selected in, so that a later
    round or hand is recognized as ending it."""

    intent: PreAction
    hand_number: int
    street: Street


@dataclass
class _Member:
    """A user who owns a seat, with the display name the table shows. The pending flags are private intents, and exist
    only for a participant of the hand in progress (a pending sit-out is cancelled by `sit_back`; a pending leave has no
    cancel). `pre_action` is the selected pre-action; `consumed` is a selection whose turn has arrived, held only until
    the end of the command that is executing it."""

    user_id: UserId
    display_name: DisplayName
    seat: int
    pending_leave: bool = False
    pending_sit_out: bool = False
    pre_action: _Selection | None = None
    consumed: PreAction | None = None


def _pre_action_options(amount_owed: int) -> tuple[PreAction, ...]:
    """The pre-actions offered at an amount owed (read from the engine's `call_obligation`)."""
    if amount_owed == 0:
        return (PreAction(PreActionKind.CHECK), PreAction(PreActionKind.CHECK_OR_FOLD))
    return (PreAction(PreActionKind.FOLD), PreAction(PreActionKind.CALL_CURRENT, amount_owed))


def _presented(intent: PreAction, amount_owed: int) -> PreAction:
    """How a stored intent presents: a `CHECK_OR_FOLD` presents as `FOLD` once chips are owed."""
    if intent.kind is PreActionKind.CHECK_OR_FOLD and amount_owed > 0:
        return PreAction(PreActionKind.FOLD)
    return intent


def _pre_action_to_action(pre_action: PreAction, legal: LegalActions) -> Action | None:
    """The engine action a pre-action becomes when its turn arrives, or None when it no longer applies and is dropped.
    The engine's own `legal_actions` decide; the engine still judges the submitted action."""
    match pre_action.kind:
        case PreActionKind.CHECK:
            return Action(ActionType.CHECK) if legal.can_check else None
        case PreActionKind.CHECK_OR_FOLD:
            return Action(ActionType.CHECK if legal.can_check else ActionType.FOLD)
        case PreActionKind.FOLD:
            return Action(ActionType.FOLD)
        case PreActionKind.CALL_CURRENT:
            return Action(ActionType.CALL) if legal.can_call and legal.amount_owed == pre_action.amount else None


def _rejected(code: RejectionCode, message: str) -> Rejected:
    return Rejected(code, message)


def _engine_rejection(error: Exception) -> Rejected | None:
    """The one place engine errors become rejections. None means the error is not mapped and must propagate."""
    message = str(error)
    match error:
        case NotPlayersTurnError() | NotShowdownTurnError() | ShowdownNotStartedError():
            return _rejected(RejectionCode.NOT_YOUR_TURN, message)
        case IllegalActionError():
            return _rejected(RejectionCode.ILLEGAL_ACTION, message)
        case HandAlreadySettledError() | GameNotStartedError():
            return _rejected(RejectionCode.NO_HAND_IN_PROGRESS, message)
        case SeatOccupiedError():
            return _rejected(RejectionCode.SEAT_TAKEN, message)
        case InvalidSeatNumber():
            return _rejected(RejectionCode.INVALID_SEAT, message)
        case InvalidPlayerCount():
            return _rejected(RejectionCode.NOT_ENOUGH_PLAYERS, message)
        case _:
            return None


def _try_engine(call: Callable[[], object]) -> Rejected | None:
    """Run the command's one fallible engine call: None when it succeeded, the mapped rejection when the engine
    rejected it, and anything unmapped propagates as a defect."""
    try:
        call()
    except Exception as error:
        rejection = _engine_rejection(error)
        if rejection is None:
            raise
        return rejection
    return None


class TableSession:
    """A transport-free private table. Build one with `create`; drive it with the commands below."""

    def __init__(
        self,
        table_id: str,
        code: str,
        settings: TableSettings,
        host_id: UserId,
        host_name: DisplayName,
        host_seat: int,
        *,
        choose_button: ButtonChooser,
    ) -> None:
        for name, text in (("table id", table_id), ("code", code)):
            if not isinstance(text, str) or text == "":
                raise ValueError(f"The {name} must be a non-empty string")
        self._table_id = table_id
        self._code = code
        self._settings = settings
        self._choose_button = choose_button
        self._table = Table(settings.max_seats)
        self._game = HoldemGame(self._table, settings.stakes)
        self._members: dict[UserId, _Member] = {}  # in join order
        self._departed: set[UserId] = set()
        self._host: UserId | None = None
        self._waiting = False
        self._revision = 1
        self._seat_new_member(host_id, host_name, host_seat)
        self._host = host_id

    @classmethod
    def create(
        cls,
        table_id: str,
        code: str,
        settings: TableSettings,
        host_id: UserId,
        host_name: DisplayName,
        host_seat: int,
        *,
        choose_button: ButtonChooser,
    ) -> TableSession:
        """Create a table with its host seated (`WAITING`, with the buy-in) at revision 1.

        Invalid input raises (`ValueError` for the identifiers, settings or table size, `InvalidSeatNumber` for the
        seat): creation is construction, not a command.
        """
        return cls(table_id, code, settings, host_id, host_name, host_seat, choose_button=choose_button)

    # --- Queries ---

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def phase(self) -> TablePhase:
        hand = self._game.hand
        if self._waiting:
            return TablePhase.WAITING_FOR_PLAYERS
        if hand is None:
            return TablePhase.NOT_STARTED
        return TablePhase.HAND_IN_PROGRESS if hand.settlement is None else TablePhase.HAND_COMPLETE

    def is_member(self, user_id: UserId) -> bool:
        return user_id in self._members

    def view_for(self, user_id: UserId) -> TableView | None:
        """The member's current view, or None for a user who is not a member."""
        member = self._members.get(user_id)
        return None if member is None else self._view(member)

    # --- Commands ---

    def join(self, user_id: UserId, expected_revision: int, display_name: DisplayName, seat: int) -> CommandResult:
        """Join and sit at `seat` with the buy-in, as a `WAITING` player."""
        if (rejection := self._stale(expected_revision)) is not None:
            return rejection
        if user_id in self._departed:
            return _rejected(RejectionCode.LEFT_TABLE, "A user who left this table cannot join it again")
        if user_id in self._members:
            return _rejected(RejectionCode.ALREADY_MEMBER, "The user is already a member")
        if any(member.display_name.conflict_key == display_name.conflict_key for member in self._members.values()):
            return _rejected(RejectionCode.DISPLAY_NAME_TAKEN, "The display name is taken at this table")
        if (rejection := _try_engine(lambda: self._seat_new_member(user_id, display_name, seat))) is not None:
            return rejection
        if self._host is None:
            self._host = user_id
        out = [self._record(TransitionCause.COMMAND)]
        return self._finish(user_id, out, resume=True)

    def leave(self, user_id: UserId, expected_revision: int) -> CommandResult:
        """Leave the table: pending for a participant of the hand in progress, otherwise at once."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        member = self._members[user_id]
        if member.pending_leave:
            return _rejected(RejectionCode.NO_CHANGE, "A leave is already pending")
        out: list[Transition] = []
        if self._in_hand_in_progress(member):
            member.pending_leave = True
            member.pending_sit_out = False  # the leave subsumes it
            member.pre_action = None
        else:
            self._remove_member(member)
            out.append(self._record(TransitionCause.COMMAND))
        return self._finish(user_id, out, resume=True)

    def sit_out(self, user_id: UserId, expected_revision: int) -> CommandResult:
        """Sit out from the next hand: pending for a participant of the hand in progress, otherwise at once."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        member = self._members[user_id]
        if member.pending_leave:
            return _rejected(RejectionCode.LEAVE_PENDING, "A leave is pending")
        if member.pending_sit_out or self._player(member).status is PlayerStatus.SITTING_OUT:
            return _rejected(RejectionCode.NO_CHANGE, "The user is already sitting out or about to")
        out: list[Transition] = []
        if self._in_hand_in_progress(member):
            member.pending_sit_out = True
        else:
            self._player(member).status = PlayerStatus.SITTING_OUT
            out.append(self._record(TransitionCause.COMMAND))
        return self._finish(user_id, out)

    def sit_back(self, user_id: UserId, expected_revision: int) -> CommandResult:
        """Cancel a pending sit-out, or sit back in (`WAITING`) from sitting out."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        member = self._members[user_id]
        if member.pending_leave:
            return _rejected(RejectionCode.LEAVE_PENDING, "A leave is pending")
        out: list[Transition] = []
        if member.pending_sit_out:
            member.pending_sit_out = False
        elif self._player(member).status is PlayerStatus.SITTING_OUT:
            self._player(member).status = PlayerStatus.WAITING
            out.append(self._record(TransitionCause.COMMAND))
        else:
            return _rejected(RejectionCode.NO_CHANGE, "The user is not sitting out")
        return self._finish(user_id, out, resume=True)

    def start_game(self, user_id: UserId, expected_revision: int) -> CommandResult:
        """Start the first hand; host only, once."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        if user_id != self._host:
            return _rejected(RejectionCode.NOT_HOST, "Only the host can start the game")
        if self.phase is not TablePhase.NOT_STARTED:
            return _rejected(RejectionCode.GAME_ALREADY_STARTED, "The game has already started")
        if (rejection := _try_engine(lambda: self._game.start(self._choose_button))) is not None:
            return rejection
        out = [self._record(TransitionCause.COMMAND)]
        return self._finish(user_id, out)

    def act(self, user_id: UserId, expected_revision: int, action: Action | ShowdownAction) -> CommandResult:
        """Pass a betting action or showdown decision to the engine unchanged; the engine decides its legality."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        seat = self._members[user_id].seat
        if (rejection := _try_engine(lambda: self._game.act(seat, action))) is not None:
            return rejection
        out = [self._record(TransitionCause.COMMAND)]
        return self._finish(user_id, out)

    def select_pre_action(self, user_id: UserId, expected_revision: int, pre_action: PreAction) -> CommandResult:
        """Select a pre-action, replacing any selection. A private intent: no revision, no transition. Only a currently
        offered option can be selected; selecting what is already presented is `NO_CHANGE`."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        member = self._members[user_id]
        if member.pending_leave:
            return _rejected(RejectionCode.LEAVE_PENDING, "A leave is pending")
        hand = self._game.hand
        if pre_action not in self._pre_action_options_for(member):
            return _rejected(RejectionCode.PRE_ACTION_UNAVAILABLE, "That pre-action is not available")
        if pre_action == self._presented_pre_action(member):
            return _rejected(RejectionCode.NO_CHANGE, "That pre-action is already selected")
        assert hand is not None and hand.betting is not None  # options are offered only in an open betting round
        member.pre_action = _Selection(pre_action, hand.number, hand.betting.street)
        return Accepted((), self._view(member))

    def clear_pre_action(self, user_id: UserId, expected_revision: int) -> CommandResult:
        """Clear the selected pre-action. A private intent: no revision, no transition."""
        if (rejection := self._check(user_id, expected_revision)) is not None:
            return rejection
        member = self._members[user_id]
        if member.pending_leave:
            return _rejected(RejectionCode.LEAVE_PENDING, "A leave is pending")
        if member.pre_action is None:
            return _rejected(RejectionCode.NO_CHANGE, "No pre-action is selected")
        member.pre_action = None
        return Accepted((), self._view(member))

    def advance_hand(self, expected_revision: int) -> CommandResult:
        """The hand boundary, accepted only when the hand is complete. The caller decides when (there are no timers).

        One shared transition, in this order: pending leaves are applied, pending sit-outs are applied, then the next
        hand starts. When too few players can play the table waits; when no `READY` player with chips is left the
        engine generation is replaced first.
        """
        if (rejection := self._stale(expected_revision)) is not None:
            return rejection
        if self.phase is not TablePhase.HAND_COMPLETE:
            return _rejected(RejectionCode.NOT_AT_HAND_BOUNDARY, "The hand is not complete")
        for member in [member for member in self._members.values() if member.pending_leave]:
            self._remove_member(member)
        for member in self._members.values():
            if member.pending_sit_out:
                member.pending_sit_out = False
                self._player(member).status = PlayerStatus.SITTING_OUT
        self._resume()
        out = [self._record(TransitionCause.HAND_BOUNDARY)]
        return self._finish(None, out)

    # --- Checks ---

    def _stale(self, expected_revision: int) -> Rejected | None:
        if expected_revision != self._revision:
            return _rejected(
                RejectionCode.STALE_REVISION, f"Expected revision {expected_revision}, but it is {self._revision}"
            )
        return None

    def _check(self, user_id: UserId, expected_revision: int) -> Rejected | None:
        """The revision, then membership: the checks every command of an existing member shares."""
        if (rejection := self._stale(expected_revision)) is not None:
            return rejection
        if user_id not in self._members:
            return _rejected(RejectionCode.NOT_A_MEMBER, "The user is not a member of this table")
        return None

    # --- Members and engine reads ---

    def _player(self, member: _Member) -> Player:
        player = self._table.get_seat(member.seat).player
        assert player is not None  # a member always owns an occupied seat
        return player

    def _in_hand_in_progress(self, member: _Member) -> bool:
        """Whether the member is a participant of a hand that is not settled; only then are intents pending."""
        hand = self._game.hand
        if hand is None or hand.settlement is not None:
            return False
        return viewer_participant_seat(self._table, hand, member.seat) is not None

    def _amount_owed(self, member: _Member) -> int | None:
        """What the member owes in the open betting round, or None when they have no obligation: no hand in progress, no
        open round, not a participant, folded or all-in. Their own turn included. Read from the engine."""
        hand = self._game.hand
        if hand is None or hand.settlement is not None or hand.betting is None:
            return None
        if viewer_participant_seat(self._table, hand, member.seat) is None:
            return None
        obligation = call_obligation(hand, member.seat)
        return None if obligation is None else obligation.amount_owed

    def _pre_action_options_for(self, member: _Member) -> tuple[PreAction, ...]:
        """The pre-actions offered to the member now: none on their own turn or with a pending leave."""
        amount_owed = self._amount_owed(member)
        if amount_owed is None or member.pending_leave or self._is_betting_actor(member):
            return ()
        return _pre_action_options(amount_owed)

    def _is_betting_actor(self, member: _Member) -> bool:
        hand = self._game.hand
        return hand is not None and hand.betting is not None and hand.betting.current_actor == member.seat

    def _presented_pre_action(self, member: _Member) -> PreAction | None:
        amount_owed = self._amount_owed(member)
        if member.pre_action is None or amount_owed is None:
            return None
        return _presented(member.pre_action.intent, amount_owed)

    def _seat_new_member(self, user_id: UserId, display_name: DisplayName, seat: int) -> None:
        self._table.sit_in(Player(user_id.value, self._settings.buy_in), seat)
        self._members[user_id] = _Member(user_id, display_name, seat)

    def _remove_member(self, member: _Member) -> None:
        """Apply a leave: stand up, record the user as departed, and pass the host role on if needed."""
        self._table.stand_up(member.seat)
        del self._members[member.user_id]
        self._departed.add(member.user_id)
        if self._host == member.user_id:
            self._host = next(iter(self._members), None)  # the earliest-joined remaining member

    # --- Boundary, waiting and reset ---

    def _resume(self) -> bool:
        """Try to start the next hand. Returns whether shared state changed: a hand started or the generation was
        replaced. The table waits when too few players can play; a failed attempt changes nothing."""
        reset = False
        if self._game.hand is not None:
            try:
                self._game.next_hand()
            except InvalidPlayerCount:
                self._waiting = True
                return False
            except GameNotStartedError:
                self._reset_generation()
                reset = True
            else:
                self._waiting = False
                return True
        try:
            self._game.start(self._choose_button)
        except InvalidPlayerCount:
            self._waiting = True
            return reset
        self._waiting = False
        return True

    def _reset_generation(self) -> None:
        """Replace the engine `Table` and `HoldemGame` (ADR 0005 §11).

        Every member keeps their seat and `player_id` and the stack they have in the old engine; a member who was
        sitting out keeps sitting out, everyone else is `WAITING`. Both objects are built before either is swapped in.
        """
        table = Table(self._settings.max_seats)
        for member in self._members.values():
            old = self._player(member)
            status = PlayerStatus.SITTING_OUT if old.status is PlayerStatus.SITTING_OUT else PlayerStatus.WAITING
            table.sit_in(Player(old.player_id, old.stack, status), member.seat)
        game = HoldemGame(table, self._settings.stakes)
        self._table = table
        self._game = game

    # --- Transitions and views ---

    def _record(self, cause: TransitionCause) -> Transition:
        """Close a shared transition: one revision increment and every member's view, captured right after it, with the
        private pre-action selections reconciled to the new state first."""
        self._revision += 1
        self._reconcile_pre_actions()
        views = {user_id: self._view(member) for user_id, member in self._members.items()}
        return Transition(self._revision, cause, MappingProxyType(views))

    def _reconcile_pre_actions(self) -> None:
        """Bring every pre-action selection up to date with the state the transition has just produced. A selection is
        cleared when its round or hand has ended, its owner can no longer act, a leave is pending, or its presentation
        is no longer offered at what is owed. One that survives to its owner's turn is consumed: it leaves the visible
        selection and is held to be executed next."""
        hand = self._game.hand
        for member in self._members.values():
            selection = member.pre_action
            if selection is None:
                continue
            amount_owed = self._amount_owed(member)
            member.pre_action = None  # kept below only while it still stands
            if amount_owed is None or member.pending_leave:
                continue
            assert hand is not None and hand.betting is not None  # an obligation exists only in an open betting round
            if (hand.number, hand.betting.street) != (selection.hand_number, selection.street):
                continue
            if _presented(selection.intent, amount_owed) not in _pre_action_options(amount_owed):
                continue
            if hand.betting.current_actor == member.seat:
                member.consumed = selection.intent
            else:
                member.pre_action = selection

    def _finish(self, requester: UserId | None, out: list[Transition], *, resume: bool = False) -> Accepted:
        """Complete an accepted command: a resume attempt while waiting, then the leaving players' automatic actions,
        each a transition of its own. `Accepted.view` is the requester's view after all of it."""
        if resume and self._waiting and self._resume():
            out.append(self._record(TransitionCause.RESUME))
        self._auto_actions(out)
        member = None if requester is None else self._members.get(requester)
        return Accepted(tuple(out), None if member is None else self._view(member))

    def _auto_actions(self, out: list[Transition]) -> None:
        """While the seat to act belongs to a member who has a pending leave or a consumed pre-action, act for them. A
        leaving player: CHECK if legal, otherwise FOLD, or MUCK at a showdown. A pre-action: the action it translates to
        under the engine's `legal_actions`; one that no longer applies is dropped and its owner keeps the turn. Each
        action is submitted to the engine like any other and is its own transition, which reconciles the others'
        pre-actions and so may hand the turn to the next one."""
        while (hand := self._game.hand) is not None:
            seat = current_actor(hand)
            member = next((m for m in self._members.values() if m.seat == seat), None)
            if member is None:
                break
            assert hand.betting is not None
            if member.pending_leave:
                if hand.betting.current_actor == member.seat:
                    kind = ActionType.CHECK if legal_actions(hand).can_check else ActionType.FOLD
                    self._game.act(member.seat, Action(kind))
                else:
                    self._game.act(member.seat, ShowdownAction.MUCK)
                out.append(self._record(TransitionCause.LEAVE_AUTO_ACTION))
            elif member.consumed is not None and hand.betting.current_actor == member.seat:
                pre_action, member.consumed = member.consumed, None
                action = _pre_action_to_action(pre_action, legal_actions(hand))
                if action is None:  # reconciliation already clears a selection that would be dropped; contract only
                    break
                self._game.act(member.seat, action)
                out.append(self._record(TransitionCause.PRE_ACTION))
            else:
                break
        for member in self._members.values():
            member.consumed = None  # a consumed pre-action never outlives the command that executes it

    def _view(self, member: _Member) -> TableView:
        by_seat = {m.seat: m for m in self._members.values()}
        seats = tuple(
            SessionSeatView(
                number=number,
                display_name=None if number not in by_seat else by_seat[number].display_name,
                is_host=number in by_seat and by_seat[number].user_id == self._host,
            )
            for number in range(1, self._settings.max_seats + 1)
        )
        return TableView(
            revision=self._revision,
            table_id=self._table_id,
            code=self._code,
            settings=self._settings,
            phase=self.phase,
            seats=seats,
            game=holdem_view(self._table, self._game.hand, member.seat),
            you=YouView(
                seat=member.seat,
                is_host=member.user_id == self._host,
                pending_leave=member.pending_leave,
                pending_sit_out=member.pending_sit_out,
                pre_action=self._presented_pre_action(member),
                pre_action_options=self._pre_action_options_for(member),
            ),
        )
