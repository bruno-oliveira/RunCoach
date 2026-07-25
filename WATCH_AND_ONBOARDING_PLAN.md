# Watch delivery & onboarding — plan for the Next and Later lanes

Follow-on to `c7cd422` (the Now lane). Written 2026-07-25.

The Now lane stopped the bleeding: adaptations now reach the watch, a week goes
up in one press, the `.fit` button no longer promises an import Garmin doesn't
have, and a plan is born with a calendar. What it did **not** do is change the
model. Send-to-watch is still something the runner initiates; RunCoach still
can't tell you what's actually on your wrist; and the coach still only notices
you trained when you press a button.

This document covers the rest.

---

## Where we are after the Now lane

| | Before | After `c7cd422` |
|---|---|---|
| Adaptation → watch | never | forward window (~8d) re-pushed on every mutation |
| Cost per week | 1 press per session | 1 press per week |
| Days removed / moved | ghosts left on the calendar | **still ghosts** — nothing is deleted |
| Beyond the 8-day window | not pushed | **still not pushed** until it enters the window |
| "Is it on my watch?" | unanswerable | **still unanswerable** |
| Runs imported | manual button | **still manual** |

The three bolded rows are what Next fixes.

---

## Next lane

### N1 — "Keep my watch in sync" (the centrepiece)

**~3–4 days.** Turns the export into a subscription. The runner flips it once at
connect time and never thinks about it again.

The groundwork is in `app/application/watch_sync_service.py`: `build_event`,
`events_in_forward_window`, and `resync_plan_to_watch` already exist and are
wired into every mutation site. N1 promotes that from a forward-window re-push
to a real reconciliation.

**Model**

- `TrainingPlan.watch_sync_enabled` (bool, default false) — the toggle. Replaces
  `watch_synced_at` as the authorisation signal; keep `watch_synced_at` as the
  "last mirrored" timestamp for the status line.
- `DailyWorkout.watch_content_hash` (str, nullable) — hash of the pushed event
  body. Makes the mirror idempotent: re-mirroring touches only days that
  genuinely changed, so API volume tracks real change rather than page loads.

**Behaviour**

1. Window widens from ~8 days to **today → +21 days**. Intervals only forwards 7
   to the device, so a longer window costs nothing on the wrist and covers a
   runner who opens the app fortnightly.
2. **Reconcile, don't just create.** Fetch the window's events once, then diff
   against the plan:
   - missing → create
   - hash changed → delete + create (the delete is what re-triggers the Garmin
     export; `_delete_existing_events` already does this correctly — preserve it)
   - present in Intervals, absent from the plan → **delete**. This is the ghost
     fix: a day that becomes rest, or moves Thursday→Saturday, currently leaves
     its old event behind forever.
3. Nightly pass rolls the window forward. Depends on N4.

**Failure surface.** One banner on the plan — *"Your watch is 2 sessions behind"*
with a Retry — not a toast that vanishes. A revoked token becomes *"Reconnect to
keep your watch in sync"*, not a 401 in the log.

**Watch for:** Intervals rate limits are undocumented. The content hash is the
mitigation; measure before the nightly job goes wide.

---

### N2 — Watch status you can trust

**~2 days.** Today the app shows an unverifiable checklist and fires a success
toast on a *calendar write*, which is not the same as reaching the watch.

- **Read the calendar back.** Show what's actually there: *"6 sessions on your
  Intervals calendar · last synced 4 minutes ago"* with a link. `GET
  /athlete/{id}/events` over the window is all it takes.
- **Gate setup before the first send, not after.** A two-step wizard (link your
  watch platform in Intervals → enable planned-workout upload) with a **Verify**
  button that confirms by reading back, instead of a checklist shown once behind
  a `localStorage` flag.
- **One honest question** after the first sync — *"Did this week appear in
  Garmin Connect?"* — branching to targeted help on "no". Better than showing
  everyone a list of toggles we can't check.
- **Per-session state.** Once `watch_content_hash` exists, each card can show
  whether it's on the wrist and at which revision. The current `is-sent` class is
  browser-session-only and lost on reload.

**Spike first:** we already `GET /athlete/{id}` for HR settings. Log the full
payload once — if it exposes Garmin/COROS link state, the wizard can verify
outright instead of asking.

---

### N3 — Stop calling it Garmin

**~3h, pure copy.** Intervals.icu forwards planned workouts to **Garmin, COROS,
Wahoo, Suunto and Zwift**. Every string in the app says Garmin — button title,
aria-label, watch-setup checklist, landing copy, i18n (en + pt). We support four
more ecosystems than we claim, at zero engineering cost.

Also state the limit honestly, up front rather than after they invest: *Polar and
Apple Watch can't receive planned workouts — you'll still get every session in
the app.* This is a destination-platform restriction, not something a different
bridge would solve.

---

### N4 — Ambient sync

**~2 days.** The precondition for everything proactive.

There is no webhook and no scheduler. `auto_map_and_adjust()` — the adaptive
engine's only trigger — runs inside the manual `/api/intervals/sync` and
`/api/strava/sync` handlers. The coach notices you trained only if you tell it to
look.

Two options:

- **Intervals webhooks** — cleanest, event-driven, no polling. Confirm what the
  platform actually offers for third-party OAuth apps.
- **A Fly cron machine** hitting an authed per-user sync endpoint. Works today,
  but note the scale-to-zero setup: the cron machine must be separate from the
  scaled-to-zero web machine.

Either way, N1's nightly window roll can ride the same trigger.

---

## Later lane

### L1 — The Today card

**~1 week.** Check-in, today's session, and watch status are one moment in the
runner's day and currently live in three places — the last one behind
`/analytics?tab=today`. Morning Check-In is positioned as the flagship
"adapts to how you feel" feature and has no daily prompt.

Fold them into a single card at the head of the plan.

### L2 — Outbound nudges

Once sync is ambient (N4) and status is trustworthy (N2), a low-readiness or
missed-week signal is worth a push notification or an email. That's the
difference between a plan you check and a coach you have.

Today every surface is pull: the proactive nudge is computed on page load, so it
can't reach someone who hasn't opened the app in four days — exactly when it
matters most.

### L3 — One consistent "what changed and why"

Same position, same voice, dismissible, every time — whether the change came from
an intent, a nudge, or an auto-adjust during a sync. The adaptation timeline
becomes the archive, not the notification. Rule: nothing changes without the
runner seeing one line about it.

### L4 — Garmin Training API

Only if RunCoach ever incorporates. Garmin states the Connect Developer Program
is **business use only** and not available to individuals or small apps. It's the
native path (it's how Runna does it), and the gate is business status rather than
technical merit — so it's a corporate decision, not an engineering one.

Not worth pursuing while Intervals covers five ecosystems for free.

---

## Ruled out — don't revisit

| Route | Why not |
|---|---|
| **Connect IQ app** | Cannot create native structured workouts. Garmin has kept this closed for years. Runna's Connect IQ artifact is a watchface, not the delivery path. |
| **`.fit` as a mainstream route** | Garmin Connect has no workout-file import, web or mobile. Only USB sideload into the device folder. Kept as a labelled power-user escape hatch. |
| **COROS API direct** | Application-gated and selective (they reject on market size). Redundant — Intervals already covers COROS. |
| **TrainingPeaks relay** | Partner-gated, and puts a paid product between RunCoach and its user. |
| **Unofficial Garmin Connect login** | Requires storing the runner's Garmin password, violates terms, breaks without notice. |

---

## Open questions to settle before building

1. **Retro-push on enable.** When a runner ticks "Upload planned workouts" *after*
   we've written events, does Intervals push the existing ones or only new ones?
   Design defensively either way: always re-mirror once the N2 wizard completes.
2. **Intervals rate limits.** Undocumented. Measure before the nightly job.
3. **Connected-service visibility.** Does `/athlete/{id}` expose Garmin/COROS link
   state? Determines whether N2 can verify or must ask.
4. **Non-Garmin parity.** Confirm the ~7-day window and create-vs-update export
   behaviour hold for COROS, Wahoo and Suunto before N3 promises them in the UI.

---

## Suggested order

```
N1 ──────────────► N2 ──► L1 ──► L2
      │                     ▲
      └──► N4 ──────────────┘
N3 (independent — ship any time, it's copy)
```

N1 first because the ghosts and the 8-day ceiling are the remaining correctness
gaps. N4 in parallel because L2 is blocked on it. N3 whenever — it's copy, and
it quadruples the addressable watch market.
