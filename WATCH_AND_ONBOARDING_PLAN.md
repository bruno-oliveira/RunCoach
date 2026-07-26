# Watch delivery & onboarding — plan for the Next and Later lanes

Follow-on to `c7cd422` (the Now lane). Written 2026-07-25.

> **Status, 2026-07-26: N1, N2, N3, L1 and L2 are built.** The mirror is a real
> reconciler, watch status is read back from Intervals, the copy names all five
> ecosystems, the Today card folds check-in + session + watch status into one
> surface, and outbound nudges can reach a runner who hasn't opened the app.
> **N4, L3 and L4 are still open.** Per-item notes are inline; the four open
> questions at the bottom were *not* answered, so the defensive fallbacks were
> built instead.
>
> **L2 settled half of N4 by necessity.** An outbound nudge needs a scheduled
> trigger, so `POST /api/notifications/run` exists and is driven by an external
> cron (the webhooks-vs-cron decision, resolved as cron — see
> `docs/outbound-nudges-setup.md`). N4's remaining half is pointing the same
> trigger at `resync_plan_to_watch` and `auto_map_and_adjust`, which is now a
> small change rather than a design question.

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

| | Before | After `c7cd422` | After N1–N3 |
|---|---|---|---|
| Adaptation → watch | never | forward window (~8d) re-pushed on every mutation | reconciled over 21d, opt-in per plan |
| Cost per week | 1 press per session | 1 press per week | 1 press, ever |
| Days removed / moved | ghosts left on the calendar | still ghosts | deleted — ours only |
| Beyond the 8-day window | not pushed | still not pushed | pushed out to 21d |
| "Is it on my watch?" | unanswerable | still unanswerable | read back from the calendar |
| Repeat mirrors of an unchanged plan | — | full re-push every time | zero API writes |
| Runs imported | manual button | still manual | **still manual — N4** |

| | After N1–N3 | After L1–L2 |
|---|---|---|
| Check-in, session, watch status | three surfaces, one behind `/analytics?tab=today` | one card at the head of the plan |
| Does the check-in change what I see? | a coach's note, on another page | a line under today's session, live |
| Can the coach reach me at all? | only if I open the app | email, when a guard genuinely fires |
| Who gets emailed by default | — | nobody: opt-in, rate-limited, unsubscribable |

---

## Where things live

Everything watch-related, so nobody has to grep for it.

| Concern | File |
|---|---|
| Today card view model + the advisory (pure) | `app/core/coaching/today_card.py` |
| Today card I/O — resolve today's session + this morning's check-in | `app/contexts/plan/plan_template_context.py` (`_build_today_card`, `today_card_for_plan`) |
| Today card markup / styles / wiring | `app/web/templates/components/today_card.html`, `app/web/static/css/plan/today-card.css`, `app/web/static/js/plan/plan_today_card.js` |
| Morning check-in (shared by the plan page and the Coach hub) | `app/web/static/js/readiness_checkin.js`, `app/web/static/css/readiness-checkin.css` |
| Outbound nudge guards + email copy (pure) | `app/core/coaching/outbound_nudge.py` |
| Outbound nudge I/O — candidates, signals, rate limit, unsubscribe tokens | `app/application/outbound_nudge_service.py` |
| Mailer port / SMTP adapter | `app/domain/notifications.py`, `app/infrastructure/notifications/mailer.py` |
| Cron trigger + unsubscribe | `app/web/routers/notifications.py`, `docs/outbound-nudges-setup.md` |
| Mirror decisions — window, ownership, hashing, diff (pure) | `app/core/training/watch_mirror.py` |
| Mirror I/O — fetch, write, record the outcome | `app/application/watch_sync_service.py` |
| Intervals HTTP client (`fetch_events`, `delete_events`, `push_workouts`, OAuth, activity sync) | `app/infrastructure/integrations/intervals_service.py` |
| Push + mirror endpoints (`push-workout`, `push-week`, `watch-sync`, `watch-resync`, `watch-status`, `watch-setup-confirm`, connect, callback) | `app/web/routers/intervals.py` |
| Plan-mutation call sites that trigger a re-sync | `app/web/routers/plan_adjustments.py` (`_resync_watch`) |
| Auto-adjust after a sync | `app/infrastructure/integrations/strava_post_sync_service.py` (`auto_map_and_adjust`) |
| Step model → Intervals workout text | `app/core/training/workout_steps/intervals_export.py` |
| `.fit` generation (sideload escape hatch) | `app/infrastructure/integrations/fit_service.py` |
| Per-workout ⌚ button | `app/web/templates/components/workout_item.html` |
| Per-week send button | `app/web/templates/components/week_card.html` |
| Watch mirror status strip (included twice — in the Today card, and standalone) | `app/web/templates/components/watch_mirror.html` |
| Watch-setup checklist + "what now" strip | `app/web/templates/plan.html` |
| Landing hero, connect card, plan form | `app/web/templates/index.html` |
| Button wiring + setup gate | `app/web/static/js/plan/plan_send_to_watch.js` |
| Mirror panel (toggle, retry, status read-back) | `app/web/static/js/plan/plan_watch_sync.js` |
| Connect flow (`connectWatch`, sync panel) | `app/web/static/js/nav.js`, `app/web/static/js/auth.js` |
| Button styles | `app/web/static/css/share.css` |
| Tests — watch | `tests/test_core/test_watch_mirror.py` (pure diff + ownership), `tests/test_services/test_watch_sync_service.py` (reconciler), `tests/test_routers/test_intervals_watch_sync_router.py` (endpoints), `tests/test_routers/test_intervals_push_router.py`, `tests/test_services/test_intervals_service.py` |
| Tests — Today card | `tests/test_core/test_today_card.py` (advisory rules), `tests/test_routers/test_today_card_router.py` (render + re-read) |
| Tests — outbound nudges | `tests/test_core/test_outbound_nudge.py` (guards + copy), `tests/test_services/test_outbound_nudge_service.py` (consent, rate limit, honest bookkeeping), `tests/test_routers/test_notifications_router.py` (trigger + unsubscribe) |

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

### N1 — "Keep my watch in sync" (the centrepiece) — ✅ BUILT

**~3–4 days.** Turns the export into a subscription. The runner flips it once at
connect time and never thinks about it again.

> **As built.** Two deviations from the sketch below, both deliberate:
>
> 1. **The content hash lives on the plan, not on `DailyWorkout`.** It's
>    `TrainingPlan.watch_event_hashes`, a JSON map of `external_id` → hash. The
>    reconciler builds its events from `plan_data`, not the ORM rows, and its
>    central question ("what did we last put on the calendar under this id?") is
>    keyed by `external_id`. It also lets the page render per-session state
>    without joining through `weekly_plans`.
> 2. **A third column, `watch_sync_error`.** The mirror runs in a background task,
>    so a failure has no response to ride back on. Without persisting the kind,
>    "Reconnect to keep your watch in sync" can't survive a reload.
>
> The pure decisions (window, ownership, hashing, diff) are in
> `app/core/training/watch_mirror.py` — split out of the service so the template
> context could use them without `contexts/` importing `application/`. The I/O
> stayed in `app/application/watch_sync_service.py`. Migration is `027`.

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

### N2 — Watch status you can trust — ✅ BUILT

> **As built.** `GET /api/intervals/watch-status` reads the window back and
> counts only events whose `external_id` is ours. When that read fails it returns
> `events_on_calendar: null` and the UI says "Couldn't check your calendar just
> now" — never a substituted number. Per-session `is-sent` now comes from the
> stored hash, so it survives a reload *and* goes false again the moment the plan
> changes.
>
> **The spike was not run** (it needs a live Garmin account), so the wizard
> *asks* rather than verifies — the plan's own fallback for open question #3.
> `User.watch_setup_confirmed_at` records the runner's word. The gate is in the
> UI, which is where the "sent!" toast is; the push endpoints were deliberately
> left un-gated so no API path starts failing on a bookkeeping flag.
>
> Still worth doing when someone has the hardware: run the `/athlete/{id}` spike
> and upgrade "ask" to "verify".

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

### N3 — Stop calling it Garmin — ✅ BUILT

> **As built.** Every user-facing string swept across all three places (template
> inline, i18n `en`, i18n `pt`), plus the CSS section comments. The Polar/Apple
> Watch limit is stated in the wizard and on the landing checklist. Remaining
> "Garmin" mentions are deliberate and correct: signing up to Intervals *with*
> Garmin, the `.fit`/USB fallback (which genuinely is Garmin-only), and the
> privacy page naming Garmin as a data source.
>
> Non-Garmin parity (open question #4) is still unconfirmed, so the copy names the
> platforms Intervals documents rather than promising identical behaviour.

**~3h, pure copy.** Intervals.icu forwards planned workouts to **Garmin, COROS,
Wahoo, Suunto and Zwift**. Every string in the app says Garmin — button title,
aria-label, watch-setup checklist, landing copy, i18n (en + pt). We support four
more ecosystems than we claim, at zero engineering cost.

Also state the limit honestly, up front rather than after they invest: *Polar and
Apple Watch can't receive planned workouts — you'll still get every session in
the app.* This is a destination-platform restriction, not something a different
bridge would solve.

---

### N4 — Ambient sync — ⬜ NOT STARTED (needs a decision first)

**~2 days.** The precondition for everything proactive.

> **Blocked on a choice, not on code.** Webhooks vs. a Fly cron machine is a
> deployment and cost decision. N1's reconciler is already idempotent and safe to
> call on a schedule — the content hash means a nightly pass over an unchanged
> plan issues zero API writes — so whichever trigger wins can just call
> `resync_plan_to_watch`. Nothing in N1 needs revisiting.

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

### L1 — The Today card — ✅ BUILT

**~1 week.** Check-in, today's session, and watch status are one moment in the
runner's day and currently live in three places — the last one behind
`/analytics?tab=today`. Morning Check-In is positioned as the flagship
"adapts to how you feel" feature and has no daily prompt.

Fold them into a single card at the head of the plan.

> **As built.** `components/today_card.html`, in the order the morning asks:
> *what am I doing → how do I feel → is it on my wrist.*
>
> - **The session block is server-rendered**, so the card is right on first
>   paint and survives a reload — the same rule N2 established for watch status.
> - **The check-in is the existing module, not a second one.**
>   `readiness_checkin.js` and its CSS moved out of `analytics/` to the shared
>   root and now have two homes; `--embedded` strips their standalone card shell
>   so nothing is a card inside a card.
> - **The payoff is one line.** `core/coaching/today_card.py` decides an
>   advisory from the readiness band and the session type, and stays silent by
>   default. `GET /api/plan/{id}/today-card` re-reads it after a check-in rather
>   than recomputing it in JS — one implementation, no drift.
> - **The advisory never claims the plan moved.** It points at *Adjust my plan*,
>   because that is still the only thing that reshapes a session.
> - The watch mirror moved into `components/watch_mirror.html` and is included
>   twice: folded into the card, and standalone when there is no "today".
>
> Putting the check-in verdict next to the session immediately exposed a lie in
> the old copy — *"your coach has eased today's guidance below"*, which was
> neither true nor, on this page, below. Fixed.

### L2 — Outbound nudges — ✅ BUILT

Once sync is ambient (N4) and status is trustworthy (N2), a low-readiness or
missed-week signal is worth a push notification or an email. That's the
difference between a plan you check and a coach you have.

Today every surface is pull: the proactive nudge is computed on page load, so it
can't reach someone who hasn't opened the app in four days — exactly when it
matters most.

> **As built.** Email over web push: push needs a granted browser permission,
> which the drifting runner is exactly the person who won't have granted.
> stdlib `smtplib` behind a port in `domain/notifications.py`, so no new
> dependency and any provider's SMTP works. Full setup:
> `docs/outbound-nudges-setup.md`.
>
> Three guards in `core/coaching/outbound_nudge.py`, highest first:
> **gone_quiet** (5+ days silent *and* ≥2 scheduled sessions passed — the only
> signal the app genuinely cannot deliver itself), **low_readiness** (3+
> consecutive check-ins ≤45), **adaptation** (the in-app nudge, forwarded rather
> than re-derived). A runner who has *never* logged a run is never told they
> went quiet — far more likely they track nowhere.
>
> **Three things stop it becoming a mailing list**, all in
> `application/outbound_nudge_service.py`: consent (`nudge_email_enabled`,
> default false, filtered in the query), a floor between emails
> (`NUDGE_MIN_INTERVAL_DAYS`, stored so it survives restarts), and a repeat
> guard (the same situation in the same words doesn't re-send).
>
> ### ⚠️ The boolean has to be honest
>
> `Mailer.send` returns whether the message was **delivered**, and the service
> records `last_nudge_email_at` only on `True`. A mailer that swallowed a
> failure and reported success would mark everyone as emailed and silence the
> real message that follows. `NullMailer` — what you get with no `SMTP_HOST` —
> returns `False` and logs at WARNING, so an unconfigured deploy mails nobody
> *and says so*. Any future adapter must keep that property.
>
> Every email carries `/unsubscribe?u=…&t=<hmac>`. The `GET` only offers; the
> `POST` acts — inboxes and scanners prefetch links, and a prefetch that
> silently flipped a preference is a bug the runner never sees.

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

> **None of the four were answered** — they need a live Garmin account, which the
> N1–N3 work did not have. Every fallback above was built instead:
>
> - **#1** — enabling sync triggers an immediate reconcile, and any later
>   reconcile re-creates whatever the calendar is missing.
> - **#2** — the content hash is in place; an unchanged plan costs zero writes.
>   **Still measure before N4's nightly job goes wide.**
> - **#3** — the wizard asks (`watch_setup_confirmed_at`) rather than verifying.
> - **#4** — the copy names the platforms Intervals documents, without claiming
>   identical export behaviour for each.
>
> They remain worth answering; none of them block N4.

---

## Suggested order

```
N1 ✅ ────────────► N2 ✅ ─► L1 ✅ ─► L2 ✅ ─► L3 ⬜
      │                                ▲
      └──► N4 ⬜ (half done) ───────────┘
N3 ✅ (independent — it was copy)
```

N1 first because the ghosts and the 8-day ceiling were the remaining correctness
gaps. N3 whenever — it's copy, and it quadruples the addressable watch market.
L2 turned out not to need N4 first: it brought its own scheduled trigger, and
that trigger is the thing N4 was blocked on.

**Next up: N4**, and it is now small. The cron machine exists (see
`docs/outbound-nudges-setup.md`); what's left is calling `resync_plan_to_watch`
and `auto_map_and_adjust` from the same schedule. N1's reconciler is already
idempotent — an unchanged plan costs zero API writes — so nothing needs
revisiting. **Measure Intervals rate limits before it goes wide** (open question
#2 below).

Then L3, which is now more visible than it was: the Today card gave "what
changed and why" an obvious home it didn't have before.
