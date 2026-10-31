# 0002: Hand lifecycle and orchestration contract

Status: Accepted (2026-10-31); partly superseded by [ADR 0003](0003-interactive-showdown-and-muck.md) (2026-10-31)

> **Supersession note (2026-10-31).** This record is kept as written. [ADR 0003](0003-interactive-showdown-and-muck.md) §11 supersedes parts of it: the Context premise that all live hands compete with no muck; `reveal_hands` in decisions 1, 2 and 7, `game/reveal.py` and `act` accepting only betting actions in decision 2, and the reveal in decision 7's list of a settled hand's own state; the `RevealKind.SHOWDOWN` river reveal and the reveal kind names in decision 4; the river order in decision 5, now a decision order; the reveal record of decision 6, replaced entirely by the showdown record; the reveal parts of decision 8; and the reveal-based Consequences. Everything else stands, including decision 3's fixed stakes for the life of a `HoldemGame`.

## Context

Milestones 0–4 provide every operation a No-Limit Texas Hold'em hand needs: starting the game and the next hand, posting blinds, dealing, applying actions, starting betting rounds, and settling. The caller sequences them. It decides when to deal the next street, when betting has closed, when to run out the board, and when to settle. Nothing records which hands are face up, nothing stops dealing or betting on a settled hand, and nothing stops a new hand from starting while the previous one is unfinished.

Milestone 5 makes the engine run a whole hand, and one hand after another. The result is a durable contract: Milestone 6 hand history, Milestone 7 bots, the future API, and clients all build on it.

Already decided: all live hands compete at showdown with no muck or concession ([ADR 0001](0001-showdown-settlement-contract.md)); being all-in does not by itself reveal hole cards; once betting is closed with at least two live players, orchestration reveals the relevant hands, completes the runout, then proceeds to showdown; runout streets are dealt without starting their betting rounds.

## Decision

1. **Two supported usage levels.**
   - The low-level operations (`initialize_betting`, `deal_hole_cards`, `apply_action`, `deal_next_street`, `start_betting_round`, `reveal_hands`, `settle_hand`) stay public. With them the caller owns sequencing.
   - With `hand_flow` and `HoldemGame` the engine owns sequencing. After a hand begins and after every action, the engine advances the hand until a player decision is required or the hand is settled. Player decisions, starting the game, and starting the next hand are the only external inputs.
   - Mixing both levels within one hand is not supported, and the engine does not try to recover from partial manual sequencing.
   - Orchestration stores no phase. Each next step is derived from hand state. This keeps the implementation simple; it is not a promise that orchestration can resume a hand someone sequenced by hand.

2. **Public entry points and placement.**
   - `game/variants/texas_holdem/hand_flow.py`: `begin_hand(hand, stakes)` and `act(hand, seat, action)`.
   - `game/variants/texas_holdem/game.py`: `HoldemGame(table, stakes)` with `start(choose_button)`, `next_hand()`, `act(seat, action)`, and the read-only current `hand`.
   - `game/variants/texas_holdem/showdown.py`: `reveal_hands(hand)`, the low-level reveal operation.
   - `game/reveal.py` is variant-agnostic. It owns `Reveal`, `RevealKind`, canonical seat ordering, and a generic show-order helper based on seat order and the last aggressor. It does not know which street or kind of showdown a show order applies to. The Hold'em showdown layer decides that.
   - No variant base class, protocol, or registry is introduced.

3. **Game lifecycle.**
   - `HoldemGame.start(choose_button)` runs `start_game`, then `begin_hand`. `next_hand()` runs `start_next_hand`, then `begin_hand`. Each returns a hand that is either waiting for a player decision or already settled. Callers of `HoldemGame` never call `begin_hand` themselves.
   - `next_hand()` is rejected with `HandInProgressError` until the current hand is settled. The rejection changes nothing.
   - Stakes are fixed for the life of a `HoldemGame`.
   - Button, participation, and zero-stack rules are the existing lifecycle rules, unchanged. When fewer than two players can play, `next_hand()` raises the existing player-count error. There is no separate game-over state.

4. **Reveal semantics.** The reveal kind reflects whether the final showdown is an all-in showdown.
   - Folded hands are never revealed. The winner of an uncontested hand is not revealed. Losing hands are never mucked automatically.
   - Before the river betting round is complete, showdown becomes certain when `is_betting_closed(hand)` with at least two live players. The reveal is `RevealKind.ALL_IN`: every live hand is revealed at once, then the remaining board is run out.
   - When the river betting round completes with at least two live players:
     - if any live player is all-in, the reveal is `RevealKind.ALL_IN`. This includes a player all-in from an earlier street while two players with chips bet through the river;
     - if no live player is all-in, the reveal is `RevealKind.SHOWDOWN`, the non-all-in river showdown, in the river show order of decision 5.
   - All-in is read after the river round is collected and before payout, so a player whose unmatched chips were returned is not all-in.
   - One Hold'em rule in `showdown.py` classifies the hand as not ready, `ALL_IN`, or `SHOWDOWN`. `reveal_hands`, `settle_hand`, and orchestration all use it.

5. **River show order.** This applies only to a `RevealKind.SHOWDOWN` reveal: the river betting round has completed with no live all-in player. The last player to bet or raise in the river betting round shows first, then the order goes clockwise. With no river bet or raise, the first live seat clockwise from the button shows first. `BettingState.last_aggressor` records the last bet or raise in the current round. It is `None` when the blinds are posted and at the start of each betting round.

6. **Reveal record.** `PokerHand.reveal` is `None` until the hand is revealed, then an immutable `Reveal(kind, seats)`. It is set at most once.
   - `RevealKind.ALL_IN`: `seats` holds every live seat in deterministic storage order, clockwise starting left of the button. This is storage order only, not a reveal sequence.
   - `RevealKind.SHOWDOWN`: `seats` is the sequential river show order.
   - The reveal is not part of `Settlement`, and ADR 0001 is unchanged.

7. **Settled-hand guard.**
   - Every public hand-level mutation entry point rejects a settled hand before any other validation: `initialize_betting`, `deal_hole_cards`, `deal_next_street`, `start_betting_round`, `apply_action`, `reveal_hands`, `settle_hand`, `begin_hand`, and `act` (and `HoldemGame.act` through it).
   - Internal helpers (`commit_chips`, `return_chips`, `collect_round`, and the payout inside settlement) rely on their guarded callers and gain no settlement dependency.
   - The error is the existing `HandAlreadySettledError`, its meaning broadened to "this hand is settled". The check and the error move to `game/poker_hand.py`, which owns the settlement marker, so betting and dealing do not depend on `settlement.py`. `settlement.py` keeps exporting the error.
   - Derived reads are unchanged: `legal_actions` already offers nothing on a settled hand.
   - This is a guard, not immutability. That hand's own state (settlement, reveal, contributions, `folded`, hole cards, board, burned cards, deck, betting state) is not changed by further operations on it. Its `HandPlayerState`s reference shared `Player` objects whose stacks and statuses change in later hands, so a settled `PokerHand` is not a durable historical snapshot. Immutable history belongs to Milestone 6.

8. **Hand start and direct settlement.**
   - `begin_hand` posts the blinds, then deals hole cards, then advances. If the blinds alone complete the preflop round, the hand can go straight to its runout and settlement.
   - A contested `settle_hand` on a hand with no reveal yet determines the reveal kind by decision 4 and records the reveal together with the settlement. Every rejectable check (settled hand, betting state, board, readiness, hole cards and ranks, the awards) completes before the reveal or any stack changes, so a rejected settlement leaves the hand unchanged, reveal included. An existing reveal is kept as it is.
   - `reveal_hands` rejects a settled hand, a hand whose showdown is not yet certain (`ShowdownNotReadyError`), a hand already revealed, and a hand with fewer than two live players.

9. **Mid-hand table changes stay outside the engine.** During a hand, callers must not stand up a hand participant and must not directly change a participant's stack. The engine's own betting and payout operations keep changing stacks as usual. This is a documented caller precondition and is not enforced. `Table` stays unaware of player status and of hands. Leaving, sitting out, timeouts, and auto-fold during a hand belong to the session and real-time milestones. A status change during a hand affects only later hands, as today.

## Alternatives considered

- **An explicit `advance(hand)` step the client calls:** gives clients control over pacing but makes them know the sequencing rules. Pacing a runout for display is a presentation concern that Milestone 6 events can serve.
- **Supporting a mix of manual and orchestrated sequencing in one hand:** needs recovery logic for states the orchestrator did not create, for no product need.
- **Storing an orchestration phase:** a second source of truth beside the hand state it would have to agree with.
- **A sequential first-to-show order for all-in showdowns:** all-in hands are tabled together, so an order there would mean nothing and would mislead history.
- **One show order for every showdown, or always clockwise from the button:** ignores the standard river rule that the last aggressor shows first, which later automatic muck would depend on.
- **Storing only the revealed seats, without the kind:** after payout clears `all_in` the kind cannot be derived, and history would mistake storage order for a reveal sequence.
- **Putting the reveal in `Settlement`:** the all-in reveal happens before the runout, before settlement exists, and ADR 0001's settlement record would change.
- **Revealing only winning hands (automatic muck):** hides information but needs player preferences. Deferred.
- **Guarding every helper, or a new error type:** adds settlement dependencies to chip and collection helpers, or two errors for one rule.
- **Enforcing seating and stack rules during a hand inside `Table`:** makes `Table` aware of hands and status, which it deliberately is not; the policy for leaving mid-hand belongs with sessions.
- **A variant-agnostic game loop now:** only one variant exists; Milestone 10 revisits per-hand variant selection.

## Consequences

- Clients and bots drive a hand only through `act` and read derived state (`legal_actions`, the current actor, `hand.reveal`, `hand.settlement`).
- Milestone 6 must record events in order, including the reveal, the runout, and facts current state loses, such as who was all-in. It must not treat `Reveal.seats` of an all-in reveal as a sequence or an old `PokerHand` as history.
- Omaha reuses `game/reveal.py` and supplies its own showdown classification and orchestration.
- Later automatic muck and voluntary show build on the river show order and the reveal record.
- Leaving or sitting out mid-hand needs a new decision in the session milestones.
