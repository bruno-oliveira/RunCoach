# Scheduled Jobs — Setup

Everything else in RunCoach is computed on page load, so it can only reach a
runner who is already looking at it. These two jobs are the exception. They run
daily from `.github/workflows/ambient-sync.yml`, in this order:

| # | Endpoint | What it does |
|---|---|---|
| 1 | `POST /api/scheduled/sync` | Imports everyone's new activities, hands them to the adaptive engine, and rolls every mirrored plan's watch window forward |
| 2 | `POST /api/notifications/run` | Emails at most one coaching nudge per opted-in runner |

**The order is load-bearing.** The `gone_quiet` guard behind step 2 asks how
long it has been since a logged run. Ask that before importing and you email
someone about a silence they ended yesterday. Step 2 only runs when step 1
succeeds — that is the default GitHub Actions behaviour, so don't add
`if: always()`.

**Nothing here is on by default.** With no `CRON_SECRET` both endpoints 404
and the workflow skips itself with a note; with no `SMTP_HOST` the mailer
refuses to send and reports the refusal; and `users.nudge_email_enabled`
defaults to false for every existing and new account. A deploy that skips this
document syncs nothing and mails nobody, which is the correct failure mode.

## Step 1 — what the sync sweep does

For every runner with an Intervals.icu or Strava connection:

1. Import activities since the stored cursor, overlapping it by a day so an
   activity uploaded late doesn't fall in the gap forever.
2. If anything new arrived, run the same `auto_map_and_adjust` the manual
   "Sync runs" button does — the plan re-paces itself without a button press.
3. Reconcile **every** plan with watch sync on, not just the ones that changed.
   The mirror window is measured from *today*, so a day passing is itself a
   change: it pulls a new day into the far edge.

Read the summary as: `runs_imported` is what came in, `plans_adapted` is how
many plans the engine touched, `reconnect_needed` counts runners whose token is
expired or missing (they look connected in the UI but sync nothing until they
reconnect — worth watching), and `failed` is contained per-runner rather than
aborting the sweep.

> **Watch `watch_plans_rolled` against Intervals.icu's rate limits.** N1's
> content hash means an unchanged plan costs zero API *writes*, but the roll
> still costs one read per mirrored plan per day. That number is undocumented
> upstream (open question #2 in `WATCH_AND_ONBOARDING_PLAN.md`) — measure
> before this grows.

## Step 2 — what gets sent

Three guards, highest priority first, in
`app/core/coaching/outbound_nudge.py`. Only the top firing guard is sent.

| Guard | Fires when | Why it's worth an inbox |
|---|---|---|
| `gone_quiet` | No logged run for 5+ days **and** ≥2 scheduled sessions passed in that window | The only signal the app genuinely cannot deliver itself — the runner isn't opening it |
| `low_readiness` | The last 3+ check-ins all scored ≤45 | A run of rough mornings before a hard session is the cheapest injury to avoid |
| `adaptation` | The in-app proactive-nudge engine fired | Forwarded, not re-derived — same wording as the banner |

A runner who has *never* logged a run is never told they've gone quiet: far
more likely they track nowhere than that they've drifted, and telling them they
missed sessions they may well have run would be plainly wrong.

## Three things stop it becoming a mailing list

1. **Consent** — `users.nudge_email_enabled`, default false, filtered in the
   candidate query rather than after the message is built. Toggled at
   Settings → Coaching emails, or by the one-click link in every email.
2. **A floor between emails** — `NUDGE_MIN_INTERVAL_DAYS` (default 4), read
   from the stored `last_nudge_email_at` so it survives restarts and holds
   across however many machines run the job.
3. **A repeat guard** — `last_nudge_email_signature`. The same situation
   restated in the same words is nagging, so a signature that hasn't changed
   doesn't send.

The bookkeeping is written **only when the mailer reports genuine delivery**.
That is why `Mailer.send` returns a bool instead of raising: a misconfigured
SMTP host must not mark everyone as emailed and silence the real message.

## 1. Configure SMTP

stdlib `smtplib`, so any provider with an SMTP endpoint works — a Gmail app
password, Resend, Postmark, SES, a local relay.

```bash
fly secrets set \
  SMTP_HOST=smtp.example.com \
  SMTP_PORT=587 \
  SMTP_USERNAME=apikey \
  SMTP_PASSWORD=... \
  SMTP_FROM='RunCoach <coach@yourdomain>' \
  PUBLIC_BASE_URL=https://runcoach.fly.dev
```

`PUBLIC_BASE_URL` is not optional in production: links inside an email are
useless relative, and the unsubscribe link is built from it.

Port 465 switches to implicit TLS automatically; anything else uses STARTTLS
unless `SMTP_STARTTLS=false`.

## 2. Set the cron secret

```bash
fly secrets set CRON_SECRET="$(openssl rand -hex 32)"
```

Until this is set, `POST /api/notifications/run` returns 404 — not 401. An
endpoint that mails real people shouldn't advertise its own existence to
someone probing for it.

## 3. Give GitHub the secret

The workflow reads `secrets.CRON_SECRET`, and optionally
`vars.PUBLIC_BASE_URL` if you deploy somewhere other than
`https://runcoach.fly.dev`:

```bash
gh secret set CRON_SECRET --body "$CRON_SECRET"
gh variable set PUBLIC_BASE_URL --body "https://runcoach.fly.dev"   # optional
```

Until the secret is set the workflow runs, notices, prints why, and passes —
rather than going red every morning on a deployment that simply hasn't turned
the feature on yet.

## 4. Check what *would* happen

`dry_run` resolves every signal, calls no provider and sends no mail, so it is
safe against production before anything goes out. Run it from the Actions tab —
**"Run workflow" defaults to dry run** — or by hand:

```bash
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  "https://runcoach.fly.dev/api/scheduled/sync?dry_run=true"
curl -X POST -H "X-Cron-Secret: $CRON_SECRET" \
  "https://runcoach.fly.dev/api/notifications/run?dry_run=true"
```

```json
{"ok": true, "dry_run": true, "candidates": 2, "runs_imported": 0,
 "users_with_new_runs": 0, "plans_adapted": 0, "watch_plans_rolled": 1,
 "watch_events_written": 0, "reconnect_needed": 0, "failed": 0}
{"ok": true, "dry_run": true, "candidates": 1, "nudged": 1, "delivered": 0,
 "skipped_rate_limited": 0, "skipped_repeat": 0, "skipped_no_signal": 0,
 "failed": 0}
```

`delivered` is the only number that means an email left the building. If
`nudged > 0` but `delivered` stays 0 on a real (non-dry) run, SMTP is
misconfigured — check the logs for `SMTP not configured` or a send failure.

## 5. Let the schedule run

`.github/workflows/ambient-sync.yml` fires at 15:00 UTC daily and is already in
the repo. Things about GitHub's scheduler worth knowing before you rely on it:

- **Schedules only run on the default branch.** A workflow edited on a branch
  doesn't take effect until it lands on `main`.
- **GitHub disables scheduled workflows after 60 days with no commits** to the
  repository. If nudges quietly stop, check that before you check the app.
- **Scheduled runs are queued, not punctual** — they can land minutes to hours
  late at peak times. Everything here is measured in days, so that's fine.
- Cron is UTC and doesn't follow DST, so the local time drifts by an hour in
  summer.

Both endpoints are safe to call more often than scheduled: imports overlap the
stored cursor, the mirror's content hash means an unchanged plan issues no
writes, and the nudge rate limit and signature mean a second run minutes later
sends nothing. The workflow's `concurrency` group stops a slow run overlapping
the next day's.

### Why not a Fly cron machine

It would work — but it has to be a *separate* machine, because `fly.toml` sets
`auto_stop_machines = 'stop'` and the web machine is asleep most of the day. A
second always-on machine costs money to do one HTTP request a day. If you'd
rather not depend on GitHub:

```bash
fly machine run alpine --schedule daily --region sjc --app runcoach \
  --env CRON_SECRET="$CRON_SECRET" \
  -- sh -c 'apk add --no-cache curl >/dev/null &&
      curl -sSf -X POST -H "X-Cron-Secret: $CRON_SECRET" \
        https://runcoach.fly.dev/api/scheduled/sync &&
      curl -sSf -X POST -H "X-Cron-Secret: $CRON_SECRET" \
        https://runcoach.fly.dev/api/notifications/run'
```

Note the `&&`: same ordering rule, same reason.

## Unsubscribing

Every email carries `/unsubscribe?u=<user_id>&t=<hmac>`. The token is an HMAC
of the user id under `SECRET_KEY` — not a JWT, because a link that lives in an
inbox forever must not expire.

The `GET` only *offers* to unsubscribe; the change is a `POST`. Mail clients
and security scanners prefetch links, and a prefetch that silently flips a
preference is a bug the runner never sees.

> Rotating `SECRET_KEY` invalidates every unsubscribe link already sitting in
> people's inboxes. They can still turn emails off in Settings, but the link
> will show "that link didn't work". Worth knowing before a rotation.

## Where things live

| Concern | File |
|---|---|
| The schedule itself | `.github/workflows/ambient-sync.yml` |
| The shared-secret gate on both endpoints | `app/dependencies/cron.py` |
| Sweep: import, adapt, roll the watch window | `app/application/ambient_sync_service.py` |
| Sweep trigger | `app/web/routers/scheduled.py` |
| Which nudge guard fires, and the email copy (pure) | `app/core/coaching/outbound_nudge.py` |
| Candidate selection, signals, rate limit, unsubscribe tokens | `app/application/outbound_nudge_service.py` |
| Mailer port | `app/domain/notifications.py` |
| SMTP adapter + the null mailer that refuses | `app/infrastructure/notifications/mailer.py` |
| Nudge trigger + unsubscribe endpoints | `app/web/routers/notifications.py` |
| Consent toggle | `app/web/templates/components/nav.html`, `app/web/static/js/nav.js` |
| Tests — sweep | `tests/test_services/test_ambient_sync_service.py`, `tests/test_routers/test_scheduled_router.py` |
| Tests — nudges | `tests/test_core/test_outbound_nudge.py`, `tests/test_services/test_outbound_nudge_service.py`, `tests/test_routers/test_notifications_router.py` |
