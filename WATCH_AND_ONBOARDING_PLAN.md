# Watch delivery & onboarding — plan for the Next and Later lanes

Follow-on to `c7cd422` (the Now lane). Written 2026-07-25.

**Reading order for someone picking this up cold:** this doc is self-contained
for *what to build*. The reasoning behind it — the cold onboarding walkthrough,
the full evaluation of every route from a plan onto a wrist, and the vendor
sources for the ruled-out options — is in the product audit that produced it.
Sources for every external claim are cited there; nothing below rests on a
sentence I couldn't attribute to Garmin, Intervals.icu, COROS or Runna's own
documentation.

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

## Where things live

Everything watch-related, so nobody has to grep for it.

| Concern | File |
|---|---|
| Mirror logic (window, event building, re-sync) | `app/application/watch_sync_service.py` |
| Intervals HTTP client (`push_workouts`, pre-delete, OAuth, activity sync) | `app/infrastructure/integrations/intervals_service.py` |
| Push endpoints (`push-workout`, `push-week`, connect, callback, status) | `app/web/routers/intervals.py` |
| Plan-mutation call sites that trigger a re-sync | `app/web/routers/plan_adjustments.py` (`_resync_watch`) |
| Auto-adjust after a sync | `app/infrastructure/integrations/strava_post_sync_service.py` (`auto_map_and_adjust`) |
| Step model → Intervals workout text | `app/core/training/workout_steps/intervals_export.py` |
| `.fit` generation (sideload escape hatch) | `app/infrastructure/integrations/fit_service.py` |
| Per-workout ⌚ button | `app/web/templates/components/workout_item.html` |
| Per-week send button | `app/web/templates/components/week_card.html` |
| Watch-setup checklist + "what now" strip | `app/web/templates/plan.html` |
| Landing hero, connect card, plan form | `app/web/templates/index.html` |
| Button wiring (single + week) | `app/web/static/js/plan/plan_send_to_watch.js` |
| Connect flow (`connectWatch`, sync panel) | `app/web/static/js/nav.js`, `app/web/static/js/auth.js` |
| Button styles | `app/web/static/css/share.css` |
| Tests | `tests/test_services/test_watch_sync_service.py`, `tests/test_routers/test_intervals_push_router.py`, `tests/test_services/test_intervals_service.py` |

**Copy lives in three places and drifts easily.** Every user-facing string
appears once inline in the template (the no-JS fallback) and once per locale in
`app/web/static/js/i18n.js`, which carries an `en` and a `pt` block. Change one
and you must change three, or the Portuguese silently keeps the old promise.
This is most of why N3 is three hours rather than twenty minutes — find the
keys with `grep -n "'watchsetup\.\|'week\.send_week'" app/web/static/js/i18n.js`.

**Migrations.** Alembic, `alembic/versions/`, convention `NNN_short_name.py`,
each declaring `down_revision` explicitly. Latest is `026_add_plan_watch_synced_at`,
so N1's is `027`. They run at startup from `app/main.py` — no manual step in
deploy, but a bad migration takes the boot down with it. Check with
`python3 -m alembic heads`.

**Exercising it against real Intervals.** `/admin` (`app/web/routers/admin.py`,
gated by `settings.admin_email`) already previews the workout text a plan day
produces and pushes it through the normal endpoint. That is the surface for
answering the open questions below — extend it rather than building throwaway
scripts.

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
   - **ours**, present in Intervals, absent from the plan → delete. This is the
     ghost fix: a day that becomes rest, or moves Thursday→Saturday, currently
     leaves its old event behind forever.
3. Nightly pass rolls the window forward. Depends on N4.

> ### ⚠️ Read this before writing the delete branch
>
> The runner's Intervals calendar is **theirs**, not ours. It holds their own
> workouts, their coach's, and events from every other app they've connected.
>
> **Only ever delete an event whose `external_id` starts with
> `runcoach-{plan_id}-`.** Never "delete everything in the window that isn't in
> the plan" — that reads naturally from the rule above and would wipe a
> stranger's training week. The current `_delete_existing_events` is safe
> because it matches against an explicit set of our own ids; any rewrite must
> keep that property.
>
> Two events can also legitimately share a date, and a runner may have manually
> edited one of our events in Intervals — deleting that is acceptable (we own
> the id), deleting the one next to it is not.
>
> Make this a test before it's a feature: seed a foreign `external_id` in the
> window and assert the reconciler leaves it untouched.

**Failure surface.** One banner on the plan — *"Your watch is 2 sessions behind"*
with a Retry — not a toast that vanishes. A revoked token becomes *"Reconnect to
keep your watch in sync"*, not a 401 in the log.

**Watch for:** Intervals rate limits are undocumented. The content hash is the
mitigation; measure before the nightly job goes wide.

**Done when**

- A foreign `external_id` seeded in the window survives a reconcile. *(Write
  this test first — see the hazard note.)*
- Turning a scheduled day into rest removes its event; no assertion on the
  runner's other events changes.
- Moving a workout Thursday→Saturday leaves exactly one event, on Saturday.
- Reconciling an unchanged plan twice issues **zero** writes the second time
  (the hash check works).
- A plan with `watch_sync_enabled = false` is never touched.
- Extend `tests/test_services/test_watch_sync_service.py` — the fixtures
  (`pushed_plan`, `_FakeIntervals`, `use_test_session`) already cover the setup.

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

**Spike first:** we already `GET /athlete/{id}` for HR settings
(`IntervalsService.fetch_athlete_settings`). Log the full payload once — if it
exposes Garmin/COROS link state, the wizard can verify outright instead of asking.

**Done when**

- The plan page states a count read back from Intervals, not a count of button
  presses — and it survives a page reload.
- A revoked token produces "Reconnect to keep your watch in sync" in the UI, not
  a silent 401. *(Reproduce by clearing `intervals_access_token` on the user.)*
- A new runner cannot reach a "sent!" toast without having passed the verify
  step.

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

Each of these needs a real answer from the platform, not a guess. All four are
answerable from `/admin` plus one Garmin account — budget half a day.

| # | Question | How to answer it | Blocks |
|---|---|---|---|
| 1 | **Retro-push on enable.** When a runner ticks "Upload planned workouts" *after* we've written events, does Intervals forward the existing ones or only new ones? | Untick the toggle in Intervals settings, push a week from `/admin`, re-tick it, and watch whether Garmin Connect receives the existing events. | N2's wizard ordering |
| 2 | **Rate limits.** Undocumented for third-party OAuth apps. | Push a 21-day window repeatedly from `/admin` and watch for 429s / throttling headers. Ask on the Intervals forum — the maintainer answers directly. | N1's nightly job |
| 3 | **Connected-service visibility.** Does `/athlete/{id}` expose Garmin/COROS link state or the upload toggle? | Log the full payload in `fetch_athlete_settings` once (it's already called on every sync) and read it. | Whether N2 verifies or asks |
| 4 | **Non-Garmin parity.** Do the ~7-day window and create-vs-update export behaviour hold for COROS, Wahoo and Suunto? | No hardware needed for the negative case: check the Intervals forum and settings UI for per-platform options. A borrowed COROS would confirm. | N3's claims in the UI |

**If a question can't be answered, design defensively rather than blocking:**
always re-mirror after the wizard (covers #1), keep the content hash so volume
stays low (covers #2), ask the runner instead of verifying (covers #3), and name
only Garmin until confirmed (covers #4).

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
