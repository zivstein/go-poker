# 0003: Interactive non-all-in showdown and muck

Status: Accepted (2026-10-31)

## Context

[ADR 0001](0001-showdown-settlement-contract.md) decided that every live hand competes at showdown, with no voluntary muck or concession. [ADR 0002](0002-hand-lifecycle-orchestration-contract.md) decided which hands are revealed and in what order: an all-in reveal, or a river showdown recorded as a sequence of reveals in the river show order. Milestone 5 Cycle 2 implemented that as `Reveal(kind, seats)`.

That does not match real play. When a non-all-in river showdown is reached, players decide in turn whether to show or to muck, and a player who mucks gives up the pot without revealing their cards. When a player is all-in, every live hand is tabled at once and nobody decides.

The showdown is a durable contract. Milestone 5 orchestration, Milestone 6 hand history, Milestone 7 bots, the future API, and clients all build on it. Orchestration is not built yet, so this is the point at which to change it.

## Decision

1. **Two showdown kinds.** Once showdown is certain, a hand has exactly one showdown, of one kind:
   - `ShowdownKind.ALL_IN`: any live player is all-in once all betting is complete, on any street. This includes a player all-in from an earlier street while two players with chips bet through the river. Every live hand is tabled at once. Nobody decides anything, the showdown is complete from the start, and the remaining board is then run out.
   - `ShowdownKind.INTERACTIVE`: the river betting round has completed with no live player all-in. Players decide in turn to SHOW or MUCK.
   - Readiness and the kind come from the one Hold'em classification rule of ADR 0002 §4, with these names. All-in is read after the river round is collected and before payout.

2. **Decision order.** In an interactive showdown, the last player to bet or raise in the river betting round decides first. With no river bet or raise, the first live seat clockwise left of the button decides first (heads-up, the big blind). Decisions continue clockwise from that seat. This is the order of ADR 0002 §5, now an order of decisions instead of reveals.

3. **SHOW and MUCK.**
   - The current decider may always SHOW or MUCK, including when deciding first and whatever has already been shown. The engine does not judge whether a shown hand already beats theirs.
   - SHOW reveals the player's hand and keeps them in contention. MUCK takes them out of contention without revealing their cards.
   - Muck is showdown state. A mucked player is not `folded`, and their betting state and contributions are unchanged.

4. **Completion.** An interactive showdown is complete when every seat has decided, or as soon as only one contender remains. That last contender is not asked to decide and wins without showing. An all-in showdown is always complete.

5. **Showdown record.** `PokerHand.showdown` replaces `PokerHand.reveal`. It is `None` until the showdown starts, then an immutable `Showdown(kind, order, decisions)`:
   - `order` holds the live seats when the showdown starts and never changes. For `ALL_IN` it is canonical storage order (clockwise starting left of the button), not a sequence. For `INTERACTIVE` it is the decision order.
   - `decisions` holds the `ShowdownAction` (`SHOW` or `MUCK`) decisions in order; `decisions[i]` belongs to `order[i]`. An `ALL_IN` showdown has none.
   - Shown seats, mucked seats, contenders, the current decider, and completion are derived, never stored. For `ALL_IN` every seat is shown. Contenders are the seats in `order` that have not mucked.
   - The showdown is started at most once. Afterwards it changes only by adding one decision at a time, never once complete.
   - It records seats and decisions, not cards. Hole cards, including mucked and unshown ones, stay in engine state; who may see them is decided by a future API projection.
   - It is not part of `Settlement`.

6. **Ownership.**
   - `game/showdown.py` replaces `game/reveal.py` and is variant-agnostic. It owns `Showdown`, `ShowdownKind`, `ShowdownAction`, the derived showdown state, the turn rule for a decision, canonical seat order, and the decision-order helper. It knows nothing about streets or variants, and does not depend on `settlement.py`.
   - Hold'em `showdown.py` owns when a showdown is ready and of which kind, `start_showdown`, `apply_showdown_action`, and `settle_hand`. It decides which seats still compete and which have ranks.
   - `game/settlement.py` awards pots among the contenders it is given. It never interprets SHOW, MUCK, or any other showdown action.

7. **Low-level operations.** Betting and showdown actions stay separate operations. There is no generic action hierarchy.
   - `start_showdown(hand)` starts the showdown explicitly; completing the river round does not start it. It rejects, in this order: a settled hand, a hand without a betting state, a showdown already started, fewer than two live players, and a hand whose showdown is not yet certain. It checks neither the board nor hole cards, so an all-in showdown starts before the runout.
   - `apply_showdown_action(hand, seat, action)` rejects, in this order: a settled hand, a hand whose showdown has not started, and a showdown that is complete or whose current decider is not `seat`. Otherwise it records the decision.
   - Both operations join the settled-hand guard of ADR 0002 §7. Each rejection leaves the hand unchanged.

8. **Settlement.**
   - `settle_hand` keeps its uncontested path for a hand with one live player. A contested hand additionally needs a complete showdown: it rejects an `INTERACTIVE` hand whose showdown has not started or still has pending decisions, leaving the hand unchanged. A contested `ALL_IN` hand with no showdown yet records its complete `ALL_IN` showdown together with the settlement, after every rejectable check, as ADR 0002 §8 decided for the reveal.
   - Only shown hands are evaluated. `Settlement.showdown_ranks` holds only shown seats; it is empty for an uncontested hand and for a contested hand that ended before anyone showed.
   - The Hold'em showdown layer passes settlement the final showdown contenders. Each pot is awarded among its eligible seats that are contenders. With one such seat it goes to that seat without consulting ranks, so an unshown last contender wins without a rank.
   - Two pot invariants hold for every settlement: every pot has at least one contender among its eligible seats, and when a pot has more than one, every one of them has a showdown rank. Settlement checks both before changing anything. A violation is an engine defect and is raised; there is no fallback payout.
   - Pot layering, side-pot eligibility as `pots()` derives it, the odd-chip rule of ADR 0001 §1, payout ownership, atomicity, and chip conservation are unchanged. `PotAward.pot` keeps the pot as derived, so its eligible seats can include a mucked seat that won nothing.

9. **Orchestration.** Orchestration (ADR 0002 §1–2) starts the showdown once it is certain, stops while a showdown decision is required, and settles once the showdown is complete, after any runout. `act` accepts a betting action or a showdown action, and a derived current actor reports whoever must decide next. The showdown is hand state, not an orchestration phase.

10. **Outside Core.** No showdown timers, automatic muck, loser detection, or client show/muck preferences.

11. **Supersession.** This ADR supersedes only these parts of the earlier ADRs, which stay as historical records:
    - ADR 0001 §2: every non-folded player competing and "no voluntary muck or concession at showdown" now hold only for an all-in showdown. "Which hands are revealed to others, and in what order, is outside this decision" is replaced by decisions 1–5 here.
    - ADR 0001 §5: `Settlement` holds each shown player's `HandRank`, not each live player's.
    - ADR 0001 §6: a contested Hold'em hand also needs a complete showdown before it can be settled.
    - ADR 0001, Alternatives considered: rejecting "allowing a player to concede at showdown" is reversed.
    - ADR 0002, Context: the premise that all live hands compete with no muck.
    - ADR 0002 §1 and §2: `reveal_hands` is replaced by `start_showdown` and `apply_showdown_action`; `game/reveal.py` and its `Reveal`, `RevealKind`, and show-order helper are replaced by `game/showdown.py`; `act` (and `HoldemGame.act`) accepts a showdown action as well.
    - ADR 0002 §4: `RevealKind.SHOWDOWN`, a non-all-in river showdown revealed in show order, is replaced by `ShowdownKind.INTERACTIVE`. The all-in rules stand under `ShowdownKind.ALL_IN`.
    - ADR 0002 §5: the river order is a decision order ("decides first", not "shows first").
    - ADR 0002 §6: the reveal record is replaced entirely by the showdown record, including "set at most once" and "ADR 0001 is unchanged".
    - ADR 0002 §7: `reveal_hands` in the guarded list is replaced by `start_showdown` and `apply_showdown_action`; the reveal in the list of a settled hand's own state is the showdown.
    - ADR 0002 §8: recording the reveal with a direct settlement now applies only to `ALL_IN`; `reveal_hands`' rejections become `start_showdown`'s.
    - ADR 0002, Consequences: clients read `hand.showdown`; history must not treat an `ALL_IN` `Showdown.order` as a sequence; SHOW/MUCK decisions are now part of the engine, while automatic muck, show/muck preferences, showdown timers, and a voluntary show by a winner who is not asked to decide remain later work.

    Everything else in ADR 0001 and ADR 0002 stands, including ADR 0002 §3's fixed stakes for the life of a `HoldemGame`.

## Alternatives considered

- **Keeping `Reveal` and adding a separate muck record:** two records describing one showdown, which can disagree.
- **Storing shown seats, mucked seats, contenders, or the current decider:** duplicate sources of truth; all are derived reliably from `order` and `decisions`.
- **Storing each decision with its seat:** the seat is already given by the decision's position in `order`.
- **Treating muck as `folded`:** fold is betting state that changes how pots are derived and what betting history means. Muck happens after betting is closed, and history must tell the two apart.
- **Passing mucked seats to settlement:** settlement would interpret a showdown action. Passing contenders keeps the boundary: the showdown decides who competes, settlement awards among them.
- **A fallback payout for a pot with no contender, or an unranked contested pot:** invents rules for a state the engine never produces and would hide a defect.
- **Starting the showdown automatically when the river round completes:** the betting layer would need to know the variant's street sequence.
- **`settle_hand` starting or deciding an interactive showdown itself:** it would make decisions on players' behalf.
- **Asking the last contender to decide:** the decision cannot change the result. A voluntary show by the winner remains deferred.
- **SHOW/MUCK decisions in an all-in showdown:** every hand is tabled; there is nothing to decide.
- **A generic action type for betting and showdown actions:** they share no behavior. Orchestration's `act` accepting either is enough.
- **Compatibility aliases for the reveal API:** two names for one truth; the engine has no external users yet.

## Consequences

- Milestone 5 Cycle 3 replaces the Cycle 2 reveal API and migrates its tests. Direct settlement of a non-all-in river showdown now needs `start_showdown` and the players' decisions first.
- Milestone 5 orchestration waits for showdown decisions as it waits for betting actions.
- Milestone 6 hand history records the showdown start, each decision in order, and the runout. It must not treat an `ALL_IN` `Showdown.order` as a sequence.
- Milestone 7 bots make showdown decisions as well as betting decisions.
- The future API projection decides who may see mucked and unshown hole cards; the engine keeps them.
- Automatic muck, showdown timers, and show/muck preferences belong to later session and real-time milestones and build on the decision order and the showdown record.
- Omaha reuses `game/showdown.py` and the generic settlement, and supplies its own classification and hand strength.
