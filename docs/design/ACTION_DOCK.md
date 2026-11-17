# Go! Poker — Action Dock Component States

**Status:** Approved by the Product Owner on 2026-11-16 as the A1 component-state specification (AM4), an M8 Web follow-up Cycle. It describes product behavior, not Web source. Its values are provisional until C4's `DESIGN_SYSTEM.md` supersedes them. The binding contract amendments are in the [C6.2 plan](../milestones/M8_C6_2_WEB_PLAN.md), revision 3 (AM1–AM3).

The Action Dock is where a seated player acts: Fold, Check or Call, choosing an amount, and committing a bet or raise. It also shows the showdown decision, the host's Start game, and the table's waiting, pending, rejection and reconnecting states.

## 1. Authority

| Layer | Holds | Rule |
| --- | --- | --- |
| Server-authoritative | `legal_actions`, `showdown_actions`, `turn`, `phase`, seats and names, `betting_structure`, `you.pending_leave`, `you.is_host` | The only source of which controls exist and of every amount and bound. The dock adds no rule and computes no amount |
| Command lifecycle | Connection phase, pending command, uncertain outcome, last rejection | Unchanged from ADR 0009 §8: one command in flight; completion only by its correlated outcome; an uncertain command is never retried |
| Local UI state | Draft text, armed Fold, arrival guard, the pressed control, menu and dialog open | Never sent, except the chosen target inside `act`. It belongs to one decision and resets with the next |
| Presentation | The displayed frame | A decision frame is always displayed at once (C6.2 §2.3 rule 6) |

## 2. Geometry

- **Two fixed rows in every state, 70 px tall** (S0 Option B, measured on 2026-11-16). Top row: the status line on the left and amount hints or chips on the right. Bottom row: the controls. The bottom row keeps its height when it is empty.
- **No layout shift.** The stage never moves when a turn starts or ends. Before A1 it moved 29 px.
- **Budget.** Header 52 px, body padding 8 px above and below, the 576 px minimum stage, and the 70 px dock make 714 px. A 1280×720 viewport fits with no vertical scroll. Below 714 px of height the page scrolls; that floor comes from the minimum stage.
- **Fixed slots, left to right:** Fold (140 px), a spacer, Check or Call (at least 128 px), the sizer (elastic), a spacer, the commit button (at least 176 px). A label change never moves a neighbouring control, and the row never wraps. The slider is the only elastic element, between 96 and 280 px.
- **Start game** sits mid-row, where the sizer will appear once the hand starts. It never sits where Fold or the commit button will appear.

## 3. States

| State | Status line | Controls |
| --- | --- | --- |
| Hero betting | "Your turn · To call $X", or "Your turn" when nothing is owed | Fold, Check or Call, sizer, commit |
| Hero showdown | "Your turn · Show or muck" | Show, Muck |
| Another player's turn | "Waiting for Bob", or "Bob to show or muck" | none |
| Seated, not in the hand | "Waiting for the next hand" | none |
| Not started | Host: none. Guest: "Waiting for the host to start" | Host: Start game |
| Waiting for players | "Waiting for players" | none |
| Hand complete | "Hand complete · Next hand starting" | none |
| Pending command | "Sending Raise to $120…" | All disabled at once; the pressed control is busy and keeps its name; the dim and spinner appear only after 150 ms |
| Rejected command | An error icon and text, as an alert, with Dismiss; `STALE_REVISION` is a quiet "Table updated." | Restored, with the draft kept |
| Reconnecting | "Reconnecting… Actions are paused." | Disabled in place; the table is dimmed |
| Uncertain outcome | "No response — reconnecting. Your last action may or may not have counted." | Disabled until the fresh `connected` snapshot |
| Pending leave | A "Leaving after this hand" chip, in the dock and the header | Unchanged; nothing offers to cancel |

A rejection clears when a newer shared revision arrives, or when the player dismisses it.

## 4. Choosing an amount and committing it

- **Selection never commits (AM1).** Min, the slider, Max and the exact-amount field only change the draft. Min and Max are quiet text controls at the slider's ends, with at least a 32×28 px hit target. They are not betting buttons.
- **The commit button is the only commit.** Its label always shows exactly the target that would be sent: "Bet $Y", "Raise to $Y", or "All-in $Y" when the draft equals `max_target` in No-Limit. Enter in the field commits the same way, through the same guards.
- **Typed amounts (AM2).** A whole number from `min_full_target` to `max_target` is committable. Anything else is invalid, and stays invalid until the player corrects it or picks Min or Max:
  - empty text;
  - text that is not a whole number;
  - below the minimum;
  - above the maximum.

  An invalid draft is never clamped, on blur or on submit, and cannot commit. The hint says why: "The maximum is $1,000". Blur only rewrites the spelling of a committable amount ("0150" becomes "150"). The slider keeps the last valid amount while the field is invalid.
- **Hint.** "Min $20 · Max $1,000" from the server's bounds. When `short_all_in_target` is set, the sizer collapses to one choice: "Your only raise: All-in $990".
- **Esc** in the field resets the draft to the minimum.
- **A new decision** starts a fresh draft at its minimum. A draft from an earlier decision is never offered or sent.
- **What a decision is.** The shared table revision is not a decision: it also changes for a join, a leave or a host change that leave the hero's choice untouched, and none of those may reset the draft, disarm Fold, restart the guard or cost focus. A decision is identified from game state: the hand (its `hand_started` event, the hero's dealt cards, and a count of the `hand_boundary` and `resume` snapshots received, because the hand `number` is display-only and may restart), its position in the hand (the log's length, which grows with every action, so a later decision with identical legal actions is a new one) and the street. Legal actions are not part of it. If the legal range changes under the same decision, the draft is revalidated: a draft still committable keeps exactly its amount, anything else restarts at the new minimum. Nothing is clamped.

## 5. Accidental-action protection

- **Turn-arrival guard (AM3).** For 350 ms after decision controls become actionable (a new decision, or the same decision after a reconnect), activations of Fold, Check or Call, the commit button, Enter in the field, and Show and Muck are ignored. The controls stay enabled and focusable (`aria-disabled`, never native `disabled`), so the guard never moves focus and the decision stays reachable. Min, Max, the slider and typing only change the draft and are not guarded. The decision is displayed and announced at once. An ignored activation is dropped, never deferred, so the guard can never send a command late or twice. A pending command or a lost connection is different: those controls are truly disabled. A rejection does not restart it. Start game is not guarded. Measured in the browser: 356 ms.
- **Fold while Check is free (D3).** The first press arms Fold. The button becomes "⚠ Confirm fold" in the error style, and the status line says "Check is free. Press Fold again to fold, or Esc to cancel." A second press folds only if it comes at least 350 ms after the first, so a double- or triple-click never folds. Esc, 4 s passing, using another dock control, or a new decision disarms it with no command. Facing a bet, Fold is one press.
- **Key repeat.** A held Enter or Space never repeats an activation, on any dock control.
- **The pressed control.** A pending command follows the control's identity, not its label: a confirmed Fold stays "Confirm fold", busy, and the status reads "Sending Fold…". A command the connection refused to send leaves nothing pressed. While Fold is armed its explanation outranks an earlier rejection; a command in flight outranks it too.

## 6. Leave

- **Placement (D4).** Leave lives in a secondary "Table" menu in the header: a disclosure, closed by Esc or a click outside. Its one item is "Leave table…", disabled while a command is in flight, while the connection is not live, and as "Leave pending" once a leave is pending.
- **Confirmation.** A native modal dialog, "Leave this table?". The rest of the page is inert. Stay is focused first, Esc means Stay, and focus returns to the menu. "⚠ Leave table" sends exactly one `leave`, and the dialog closes only once the connection reports it was sent. If the connection is not live, a command is in flight or the send is refused, the dialog stays open and says "Nothing was sent". The outcome still comes only from the server.
- **Copy.** Only documented server behavior; it never promises a rejoin and never mentions chips:
  - always: "You'll give up seat N. Leaving can't be undone or cancelled.";
  - on your turn: "It's your turn: leaving now checks if you can, otherwise folds, right away.", or, at your showdown decision, "…leaving now mucks your cards right away.";
  - in the hand with live cards: "Until this hand ends, the table checks or folds for you on your turns and mucks your cards if you're asked to show. You'll leave when the hand ends.";
  - folded: "You'll leave when this hand ends.";
  - a host with others seated: "The host role passes to another player."

## 7. Keyboard, focus and announcements

- The dock never takes focus when a turn arrives. A polite live region says "Your turn. To call $X."
- Tab order follows the visual order.
- If the focused control is disabled by a pending command, focus moves to the dock itself, never to the page.
- The armed Fold is announced politely. A rejection is an alert.

## 8. Deferred

- **Slider increments.** The slider moves in $1 steps across the legal range. Stepping by the small blind needs an owner decision (A1 report): the engine accepts every whole-number target in the range, and no chip denomination exists, so snapping would be client-computed amounts under C6.2 §2.3 rule 7.
- **Bet presets** (2 BB, ½ Pot, 3×): only from the authoritative game contract or server-provided targets (W21). None is rendered until then. A preset row would select a draft only, never commit, and be absent or disabled with no valid server target. It fits in the top row's hint area or needs a taller dock, which the 714 px budget does not allow at 1280×720.
- **Display-only arithmetic** ("adds $X", "$Y behind"): deferred (D1); rule 7 is unchanged.
- **Also deferred:** pre-actions, keyboard shortcuts, the action timer, player action feedback on the table (A2), and motion.
