"""A deterministic, seeded `TableSession` stress driven only through the public commands.

Each seed plays a few hundred random, mostly legal commands (joins, leaves, sit-outs and sit-backs, betting and
showdown decisions, `advance_hand`, pre-action selections and clears, stale revisions and invalid inputs) on a
short-stacked table, so that busts, all-ins, waiting and generation resets all happen. After every command it checks the
invariants below; the engine is read only to cross-check the views and the rejection atomicity.

Pre-actions are checked against a model kept from the public views only: what each member selected, and the rules of
the spec (a selection survives a transition only while its presentation is still offered, in the same hand and street,
without a pending leave; one whose owner's turn arrived is executed as the very next transition).
"""

from dataclasses import fields, is_dataclass, replace
from random import Random

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.app.results import Accepted, CommandResult, Rejected, TransitionCause
from go_poker.app.session import TableSession
from go_poker.app.views import TablePhase, TableSettings, TableView
from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.stakes import Stakes
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.view import TurnKind, holdem_view

MAX_SEATS = 5
USERS = tuple(UserId(f"uid-u{i}-9c2e") for i in range(8))
DISPLAY_NAMES = {user_id: DisplayName(f"User{i}") for i, user_id in enumerate(USERS)}
SEEDS = range(40)
STEPS = 260
CALM_STEPS = 150
PRE_ACTION_RATE = 0.4  # while someone has options

CHECK_PA = PreAction(PreActionKind.CHECK)
CHECK_OR_FOLD_PA = PreAction(PreActionKind.CHECK_OR_FOLD)
FOLD_PA = PreAction(PreActionKind.FOLD)
GUESSES = (CHECK_PA, CHECK_OR_FOLD_PA, FOLD_PA, *(PreAction(PreActionKind.CALL_CURRENT, n) for n in (5, 10, 15, 40)))


def offered(owed: int) -> tuple[PreAction, ...]:
    """The spec's table of options at an amount owed, restated here independently of the implementation."""
    if owed == 0:
        return (CHECK_PA, CHECK_OR_FOLD_PA)
    return (FOLD_PA, PreAction(PreActionKind.CALL_CURRENT, owed))


def presented(intent: PreAction, owed: int) -> PreAction:
    return FOLD_PA if intent == CHECK_OR_FOLD_PA and owed > 0 else intent


def owed_seen_by(view: TableView) -> int | None:
    """What the viewer owes, read from their own view: from the legal actions on their turn, otherwise from the offered
    options (None when none are offered)."""
    hand = view.game.hand
    if hand is not None and hand.turn is not None and hand.turn.kind is TurnKind.BETTING:
        if hand.turn.seat == view.you.seat:
            assert hand.legal_actions is not None
            return hand.legal_actions.amount_owed
    options = view.you.pre_action_options
    if not options:
        return None
    return 0 if CHECK_PA in options else options[1].amount


@pytest.fixture(autouse=True)
def seeded_shuffles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shuffle every deck from one seeded stream (Deck's own seam), so a seed replays the same hands and winners."""
    rng = Random(20260311)
    original = Deck.shuffle
    monkeypatch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=rng))


def walk(value: object):  # type: ignore[no-untyped-def]
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from walk(getattr(value, field.name))
    elif isinstance(value, tuple | list | frozenset | set):
        for item in value:
            yield from walk(item)


def seat_stack(view: TableView) -> int:
    occupant = view.game.seats[view.you.seat - 1].occupant
    assert occupant is not None
    return occupant.stack


def chips_in_play(view: TableView) -> int:
    """Chips at the seats, in front of the participants and in the collected pots, from one member's view."""
    seated = sum(seat.occupant.stack for seat in view.game.seats if seat.occupant is not None)
    hand = view.game.hand
    if hand is None or hand.settlement is not None:
        return seated
    return seated + sum(p.in_front for p in hand.participants) + sum(pot.amount for pot in hand.pots)


class Stress:
    def __init__(self, seed: int) -> None:
        self.rng = Random(seed)
        buy_in = self.rng.choice([20, 45, 100, 400])
        settings = TableSettings(Stakes(5, 10), buy_in, MAX_SEATS)
        self.buy_in = buy_in
        host = USERS[0]
        self.session = TableSession.create(
            "t", "CODE", settings, host, DISPLAY_NAMES[host], 1, choose_button=lambda seats: self.rng.choice(seats)
        )
        self.bank = buy_in
        self.departed: set[UserId] = set()
        self.snapshots: list[tuple[object, str]] = []
        self.seen: set[object] = set()
        self.last_hand: tuple[int, int] | None = None  # (id of the game, hand number)
        self.model: dict[UserId, tuple[PreAction, int, Street]] = {}  # selected intent, its hand number and street
        self.longest_pre_action_cascade = 0  # of the last command: the most consecutive PRE_ACTION transitions

    # --- observation ---

    def members(self) -> list[UserId]:
        return [u for u in USERS if self.session.is_member(u)]

    def fingerprint(self) -> tuple[object, ...]:
        s = self.session
        table, game = s._table, s._game  # noqa: SLF001
        seats = tuple(
            (n, None if (p := table.get_seat(n).player) is None else (p.player_id, p.stack, p.status))
            for n in range(1, MAX_SEATS + 1)
        )
        members = tuple(
            (m.user_id, m.seat, m.pending_leave, m.pending_sit_out, m.pre_action, m.consumed)
            for m in s._members.values()  # noqa: SLF001
        )
        views = tuple(s.view_for(u) for u in USERS)
        return (s.revision, s.phase, views, repr(game.hand), seats, members, s._host, s._waiting, id(game))  # noqa: SLF001

    # --- command choice ---

    def current_actor(self) -> tuple[UserId, TableView] | None:
        for user in self.members():
            view = self.session.view_for(user)
            assert view is not None
            hand = view.game.hand
            if self.session.phase is TablePhase.HAND_IN_PROGRESS and hand is not None and hand.turn is not None:
                if hand.turn.seat == view.you.seat:
                    return user, view
        return None

    def pick_action(self, view: TableView) -> Action | ShowdownAction:
        hand = view.game.hand
        assert hand is not None
        if hand.showdown_actions is not None:
            return self.rng.choice(hand.showdown_actions)
        legal = hand.legal_actions
        assert legal is not None
        options: list[Action] = []
        if legal.can_fold:
            options.append(Action(ActionType.FOLD))
        if legal.can_check:
            options += [Action(ActionType.CHECK)] * 3
        if legal.can_call:
            options += [Action(ActionType.CALL)] * 3
        for flag, kind in ((legal.can_bet, ActionType.BET), (legal.can_raise, ActionType.RAISE)):
            if flag and legal.max_target is not None:
                low = legal.short_all_in_target or legal.min_full_target or legal.max_target
                target = self.rng.choice([low, legal.max_target, self.rng.randint(low, legal.max_target)])
                options.append(Action(kind, target))
        return self.rng.choice(options)

    def random_command(self) -> tuple[str, CommandResult]:
        s, rng = self.session, self.rng
        revision = s.revision if rng.random() < 0.93 else s.revision + rng.choice([-1, 1, 7])
        members, phase = self.members(), s.phase
        choosers = [u for u in members if (v := s.view_for(u)) is not None and v.you.pre_action_options]
        if members and rng.random() < (PRE_ACTION_RATE if choosers else 0.04):
            return self.pre_action_command(revision, members, choosers)
        actor = self.current_actor()
        roll = rng.random()
        if phase is TablePhase.HAND_COMPLETE and roll < 0.55:
            return "advance", s.advance_hand(revision)
        if actor is not None and roll < 0.6:
            return "act", s.act(actor[0], revision, self.pick_action(actor[1]))
        if roll < 0.62:
            return "advance", s.advance_hand(revision)
        if roll < 0.70:
            user = rng.choice(USERS)
            return "join", s.join(user, revision, DISPLAY_NAMES[user], rng.randint(0, MAX_SEATS + 1))
        if roll < 0.75:
            host = next((m for m in members if m == s._host), None)  # noqa: SLF001
            return "start", s.start_game(host or rng.choice(USERS), revision)
        user = rng.choice(members + list(USERS[:2]) if members else list(USERS))
        if roll < 0.80:
            return "leave", s.leave(user, revision)
        if roll < 0.90:
            return "sit_out", s.sit_out(user, revision)
        if roll < 0.96:
            return "sit_back", s.sit_back(user, revision)
        stranger = rng.choice(members) if members else USERS[0]
        return "act-any", s.act(stranger, revision, self.pick_action_any())

    def pre_action_command(
        self, revision: int, members: list[UserId], choosers: list[UserId]
    ) -> tuple[str, CommandResult]:
        """Select (mostly an offered option, sometimes any guess) or clear, for a member who has options when there is
        one, or sometimes any member or a stranger."""
        s, rng = self.session, self.rng
        user = rng.choice(choosers) if choosers and rng.random() < 0.85 else rng.choice(members)
        if rng.random() < 0.03:
            user = USERS[-1]
        if rng.random() < 0.15:
            return "clear_pre_action", s.clear_pre_action(user, revision)
        view = s.view_for(user)
        pool = view.you.pre_action_options if view is not None and rng.random() < 0.8 else ()
        return "select_pre_action", s.select_pre_action(user, revision, rng.choice(pool or GUESSES))

    def pick_action_any(self) -> Action | ShowdownAction:
        return self.rng.choice(
            [Action(ActionType.FOLD), Action(ActionType.CHECK), Action(ActionType.CALL), ShowdownAction.SHOW]
        )

    # --- invariants ---

    def step(self) -> None:
        s = self.session
        before_fp = self.fingerprint()
        before_revision = s.revision
        before_members = {u: s.view_for(u) for u in self.members()}
        before_stacks = {uid: seat_stack(v) for uid, v in before_members.items() if v is not None}
        before_phase = s.phase
        name, result = self.random_command()
        if isinstance(result, Rejected):
            assert result.message
            assert self.fingerprint() == before_fp, (name, result)
            return
        if name in ("select_pre_action", "clear_pre_action"):
            self.check_private_pre_action(name, result, before_members)
            return
        self.check_accepted(name, result, before_revision, before_members, before_stacks, before_phase)

    def check_private_pre_action(self, name: str, result: Accepted, before: dict[UserId, TableView | None]) -> None:
        """A select or clear is private: no transition, the revision stays, nobody else's view changes in any way, and
        the owner's view differs only in their own selection."""
        s = self.session
        assert result.transitions == ()
        assert result.view is not None and result.view.revision == s.revision
        owners = [u for u in self.members() if s.view_for(u) != before[u]]
        assert len(owners) == 1, (name, owners)
        owner = owners[0]
        after = s.view_for(owner)
        assert after == result.view and before[owner] is not None and after is not None
        assert replace(after, you=replace(after.you, pre_action=None)) == replace(
            before[owner],
            you=replace(before[owner].you, pre_action=None),  # type: ignore[union-attr]
        )
        assert after.you.pre_action != before[owner].you.pre_action  # type: ignore[union-attr]
        if name == "clear_pre_action":
            self.model.pop(owner, None)
            assert after.you.pre_action is None
        else:
            hand = after.game.hand
            assert hand is not None and after.you.pre_action is not None
            assert after.you.pre_action in after.you.pre_action_options
            # the selection that was made is the one the view shows, up to the CHECK_OR_FOLD presentation
            self.model[owner] = (self.last_selected(after), hand.number, hand.street)
        self.check_pre_action_model_live()
        self.seen.add((name, ()))

    def last_selected(self, view: TableView) -> PreAction:
        """The intent a successful select stored: what the view presents. CHECK_OR_FOLD shows as FOLD only once chips
        are owed, and it cannot be selected then, so a fresh selection is presented exactly as selected."""
        assert view.you.pre_action is not None
        return view.you.pre_action

    def check_pre_action_model_live(self) -> None:
        """The live views match the model (the state a private command or a finished command leaves behind)."""
        for user in self.members():
            view = self.session.view_for(user)
            assert view is not None
            self.step_model(user, view)

    def step_model(self, user: UserId, view: TableView) -> bool:
        """Apply one shared state to the model for one member and check the member's view against it. True when the
        member's selection survived to their own turn, which means it must be executed as the next transition."""
        you, hand = view.you, view.game.hand
        selection = self.model.get(user)
        on_turn = (
            hand is not None
            and hand.turn is not None
            and hand.turn.kind is TurnKind.BETTING
            and hand.turn.seat == you.seat
        )
        owed = owed_seen_by(view)
        if on_turn:
            assert you.pre_action is None and you.pre_action_options == ()
        elif you.pre_action_options:
            assert you.pre_action_options == offered(owed)  # type: ignore[arg-type]
        else:
            assert you.pre_action is None
        if you.pre_action is not None:
            assert you.pre_action in you.pre_action_options  # a visible selection is an offered option
            assert hand is not None and hand.settlement is None and not you.pending_leave
        if selection is None:
            assert you.pre_action is None
            return False
        intent, number, street = selection
        if hand is None or owed is None or you.pending_leave or (hand.number, hand.street) != (number, street):
            del self.model[user]
            assert you.pre_action is None
            self.seen.add("cleared: round or hand ended, or the seat cannot act, or a leave")
            return False
        if presented(intent, owed) not in offered(owed):
            del self.model[user]
            assert you.pre_action is None
            self.seen.add(f"cleared: {intent.kind.name} no longer offered")
            return False
        if on_turn:
            del self.model[user]
            self.seen.add(f"consumed: {intent.kind.name}")
            return True
        assert you.pre_action == presented(intent, owed)
        if intent != you.pre_action:
            self.seen.add("survived: CHECK_OR_FOLD presenting as FOLD")
        return False

    def check_cascade_model(self, result: Accepted) -> None:
        """Step the model through each transition of a command: reconciled in the transition itself, and a selection
        whose turn arrived is executed by exactly the next transition, which is a `PRE_ACTION` one."""
        transitions = result.transitions
        run = longest = 0
        for transition in transitions:
            run = run + 1 if transition.cause is TransitionCause.PRE_ACTION else 0
            longest = max(longest, run)
        self.longest_pre_action_cascade = longest
        due: tuple[UserId, TableView] | None = None  # (owner, the view in which their turn arrived)
        for index, transition in enumerate(transitions):
            if due is not None:
                assert transition.cause is TransitionCause.PRE_ACTION, (index, [t.cause for t in transitions])
                owner, before = due
                self.check_executed(before, transition.views[owner])
            else:
                assert transition.cause is not TransitionCause.PRE_ACTION, [t.cause for t in transitions]
            due = None
            for user, view in transition.views.items():
                if self.step_model(user, view):
                    assert due is None  # one actor at a time
                    due = (user, view)
        assert due is None  # nothing is left waiting for a next transition
        for user in list(self.model):
            if not self.session.is_member(user):
                del self.model[user]

    @staticmethod
    def check_executed(before: TableView, after: TableView) -> None:
        """The executed pre-action did what the selection said: folded for a fold, a check kept the stack, a call spent
        chips. The owner's stack and fold flag are read from the two views."""
        assert before.game.hand is not None and after.game.hand is not None
        seat = before.you.seat
        legal = before.game.hand.legal_actions
        assert legal is not None
        was = before.game.seats[seat - 1].occupant
        now = after.game.seats[seat - 1].occupant
        assert was is not None and now is not None
        folded = next(p.folded for p in after.game.hand.participants if p.seat == seat)
        settled = after.game.hand.settlement is not None  # an action can end an all-in hand, which pays out at once
        if legal.can_check:
            assert not folded and (now.stack == was.stack or settled)  # nothing owed: only a check can have been run
        else:
            assert folded or now.stack < was.stack or settled  # folded, or called

    def check_accepted(
        self,
        name: str,
        result: Accepted,
        before_revision: int,
        before_members: dict[UserId, TableView | None],
        before_stacks: dict[UserId, int],
        before_phase: TablePhase,
    ) -> None:
        s = self.session
        # Revisions: one per shared transition, consecutive, ending at the live revision; none without a transition.
        revisions = [t.revision for t in result.transitions]
        assert revisions == list(range(before_revision + 1, before_revision + 1 + len(revisions))), (name, revisions)
        assert s.revision == before_revision + len(revisions)
        if name in ("advance",):
            assert [t.cause for t in result.transitions] == [TransitionCause.HAND_BOUNDARY]
        causes = [t.cause for t in result.transitions]
        assert all(c is TransitionCause.LEAVE_AUTO_ACTION for c in causes if c not in self.allowed_causes(name))
        assert causes.count(TransitionCause.RESUME) <= 1 and causes.count(TransitionCause.HAND_BOUNDARY) <= 1
        if not result.transitions:
            assert name in ("leave", "sit_out", "sit_back"), name  # only private intents are silent
            assert result.view is not None  # a private intent returns the requester's view

        # Membership bookkeeping: chips leave with a departed member; a departed user never returns.
        now = set(self.members())
        for uid in set(before_members) - now:
            self.bank -= before_stacks[uid]
            self.departed.add(uid)
        for uid in now - set(before_members):
            self.bank += self.buy_in
            assert uid not in self.departed
        assert not (now & self.departed)

        # Every transition: its views are those of the members at that moment and carry its revision.
        for transition in result.transitions:
            assert set(transition.views) <= now | self.departed
            for view in transition.views.values():
                assert view.revision == transition.revision
                self.check_view(view)
        if result.transitions:
            assert set(result.transitions[-1].views) == now
            self.snapshots.append((result.transitions, repr(result.transitions)))

        # Accepted.view: the requester's final view; None only for advance_hand or after leaving.
        if name == "advance":
            assert result.view is None
        elif result.view is not None:
            assert result.view.revision == s.revision
        # The live state.
        live = {u: s.view_for(u) for u in self.members()}
        for uid, view in live.items():
            assert view is not None
            if result.transitions:
                assert result.transitions[-1].views[uid] == view
            self.check_live_view(view)
        self.check_table(live)
        self.check_cascade_model(result)
        self.check_pre_action_model_live()
        assert all(m.consumed is None for m in s._members.values())  # noqa: SLF001
        self.check_hand_numbers()
        self.seen.add((name, tuple(c.name for c in causes)))
        if s.phase is TablePhase.WAITING_FOR_PLAYERS:
            self.seen.add("waiting")
        if before_phase is TablePhase.HAND_COMPLETE and s.phase is TablePhase.HAND_IN_PROGRESS:
            self.seen.add("next-hand")

    @staticmethod
    def allowed_causes(name: str) -> set[TransitionCause]:
        return {
            TransitionCause.COMMAND,
            TransitionCause.RESUME,
            TransitionCause.HAND_BOUNDARY,
            TransitionCause.PRE_ACTION,
        }

    def check_view(self, view: TableView) -> None:
        """No user id anywhere; the cards of the view are only its own, the board and the shown ones."""
        text = repr(view)
        assert "uid-" not in text and "player_id" not in text
        assert not any(isinstance(item, UserId) for item in walk(view))
        hand = view.game.hand
        if hand is None:
            return
        shown = set(hand.showdown.shown) if hand.showdown is not None else set()
        for p in hand.participants:
            if p.hole_cards is not None:
                assert p.seat == view.you.seat or p.seat in shown, (p.seat, view.you.seat)
            else:
                assert p.strength is None
        allowed: set[Card] = set(hand.board)
        allowed |= {c for p in hand.participants if p.hole_cards for c in p.hole_cards}
        assert {item for item in walk(view) if isinstance(item, Card)} <= allowed
        # pending intents only for the hand's participants, and never both
        assert not (view.you.pending_leave and view.you.pending_sit_out)
        if view.you.pending_leave or view.you.pending_sit_out:
            assert view.phase in (TablePhase.HAND_IN_PROGRESS, TablePhase.HAND_COMPLETE)
            assert view.you.seat in {p.seat for p in hand.participants}

    def check_live_view(self, view: TableView) -> None:
        s = self.session
        assert view.game == holdem_view(s._table, s._game.hand, view.you.seat)  # noqa: SLF001
        hand = s._game.hand  # noqa: SLF001
        if hand is not None and view.game.hand is not None:
            truth = {st.seat_number: tuple(st.hole_cards) for st in hand.players}
            for p in view.game.hand.participants:
                if p.hole_cards is not None:
                    assert p.hole_cards == truth[p.seat]
            assert view.game.hand.board == tuple(hand.board)
            burned = {c for c in getattr(hand, "burned_cards", ())}
            assert not ({i for i in walk(view) if isinstance(i, Card)} & burned)

    def check_table(self, live: dict[UserId, TableView | None]) -> None:
        s = self.session
        views = [v for v in live.values() if v is not None]
        assert len({id(v) for v in views}) == len(views)
        for view in views:
            first = views[0]
            assert (view.revision, view.phase, view.seats, view.settings) == (
                first.revision,
                first.phase,
                first.seats,
                first.settings,
            )
            assert view.game.seats == first.game.seats
            assert view.phase is s.phase
        if views:
            assert sum(v.you.is_host for v in views) == 1
            assert sum(seat.is_host for seat in views[0].seats) == 1
            assert sorted(v.you.seat for v in views) == sorted(
                seat.number for seat in views[0].seats if seat.display_name is not None
            )
            assert chips_in_play(views[0]) == self.bank, (s.phase, self.bank)
            if s.phase is TablePhase.HAND_IN_PROGRESS:
                actor = self.current_actor()
                assert actor is not None and not actor[1].you.pending_leave  # a leaver never waits on their turn
            if s.phase in (TablePhase.NOT_STARTED, TablePhase.WAITING_FOR_PLAYERS):
                assert not any(v.you.pending_leave or v.you.pending_sit_out for v in views)

    def check_hand_numbers(self) -> None:
        game = self.session._game  # noqa: SLF001
        hand = game.hand
        if hand is None:
            self.last_hand = None
            return
        current = (id(game), hand.number)
        if self.last_hand is not None and current != self.last_hand:
            if current[0] == self.last_hand[0]:
                assert hand.number == self.last_hand[1] + 1  # consecutive within a generation
            else:
                assert hand.number == 1  # numbers restart in a fresh generation
        elif self.last_hand is None:
            assert hand.number == 1 or self.session.revision > 1
        self.last_hand = current

    def finish(self) -> None:
        # Transitions captured earlier were not changed by later play (views are values).
        for transitions, text in self.snapshots:
            assert repr(transitions) == text


class CalmStress(Stress):
    """A fuller table with little churn, so hands run long enough for selections to be made, invalidated and executed:
    the same invariants as `Stress`, and mostly betting and pre-action commands."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        for user in USERS[1:MAX_SEATS]:
            joined = self.session.join(user, self.session.revision, DISPLAY_NAMES[user], USERS.index(user) + 1)
            assert isinstance(joined, Accepted)
            self.bank += self.buy_in
        started = self.session.start_game(USERS[0], self.session.revision)
        assert isinstance(started, Accepted)

    def pick_action(self, view: TableView) -> Action | ShowdownAction:
        """Raises more often than the base, so that selected calls are invalidated by re-raises."""
        hand = view.game.hand
        assert hand is not None
        legal = hand.legal_actions
        if legal is not None and legal.can_raise and legal.min_full_target is not None and self.rng.random() < 0.3:
            return Action(ActionType.RAISE, legal.min_full_target)
        return super().pick_action(view)

    def random_command(self) -> tuple[str, CommandResult]:
        s, rng = self.session, self.rng
        revision = s.revision if rng.random() < 0.97 else s.revision + rng.choice([-1, 1])
        members = self.members()
        actor = self.current_actor()
        roll = rng.random()
        if not members:
            user = rng.choice(USERS)
            return "join", s.join(user, revision, DISPLAY_NAMES[user], rng.randint(1, MAX_SEATS))
        if s.phase is TablePhase.HAND_COMPLETE:
            return "advance", s.advance_hand(revision)
        choosers = [u for u in members if (v := s.view_for(u)) is not None and v.you.pre_action_options]
        if choosers and roll < 0.45:
            return self.pre_action_command(revision, members, choosers)
        if actor is not None and roll < 0.93:
            return "act", s.act(actor[0], revision, self.pick_action(actor[1]))
        user = rng.choice(members)
        if roll < 0.95:
            return "leave", s.leave(user, revision)
        if roll < 0.98:
            return "sit_out", s.sit_out(user, revision)
        return "sit_back", s.sit_back(user, revision)


@pytest.mark.parametrize("seed", range(12))
def test_calm_sessions_keep_every_invariant_and_every_pre_action_rule(seed: int) -> None:
    stress = CalmStress(seed)
    for _ in range(CALM_STEPS):
        stress.step()
    stress.finish()


def test_the_calm_sessions_reach_every_pre_action_path() -> None:
    """Guard against a vacuous pre-action stress: every kind is selected, executed and invalidated, in cascades."""
    seen: set[object] = set()
    cascades = 0
    for seed in range(6):
        stress = CalmStress(seed)
        for _ in range(CALM_STEPS):
            stress.step()
            cascades += stress.longest_pre_action_cascade >= 2
        seen |= stress.seen
    assert cascades > 0
    for expected in (
        "cleared: round or hand ended, or the seat cannot act, or a leave",
        "cleared: CHECK no longer offered",
        "cleared: CALL_CURRENT no longer offered",
        "consumed: CHECK",
        "consumed: CHECK_OR_FOLD",
        "consumed: FOLD",
        "consumed: CALL_CURRENT",
        "survived: CHECK_OR_FOLD presenting as FOLD",
    ):
        assert expected in seen, expected


@pytest.mark.parametrize("seed", SEEDS)
def test_seeded_sessions_keep_every_invariant_through_random_public_commands(seed: int) -> None:
    stress = Stress(seed)
    for _ in range(STEPS):
        stress.step()
    stress.finish()


def test_the_seeded_sessions_actually_reach_the_interesting_states() -> None:
    """Guard against a vacuous stress: waiting, automatic actions, resumes and next hands occur in the first seeds."""
    seen: set[object] = set()
    resets = 0
    for seed in list(SEEDS)[:20]:
        stress = Stress(seed)
        generations = {id(stress.session._game)}  # noqa: SLF001
        for _ in range(STEPS):
            stress.step()
            generations.add(id(stress.session._game))  # noqa: SLF001
        resets += len(generations) - 1
        seen |= stress.seen
    flat = {c for item in seen if isinstance(item, tuple) for c in item[1]}
    assert {"LEAVE_AUTO_ACTION", "RESUME", "HAND_BOUNDARY"} <= flat
    assert {"waiting", "next-hand"} <= seen
    assert resets > 0
    assert any(isinstance(item, tuple) and item[0] == "leave" and not item[1] for item in seen)  # a private leave
