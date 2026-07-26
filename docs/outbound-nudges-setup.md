# Outbound Coaching Nudges — Setup

Every other coaching surface in RunCoach is computed on page load, so it can
only reach a runner who is already looking at it. Outbound nudges are the one
exception: a scheduled job evaluates each opted-in runner and, at most once
every few days, emails the single most useful thing it found.

**Nothing here is on by default.** With no `SMTP_HOST` the mailer refuses to
send and reports the refusal; with no `CRON_SECRET` the trigger endpoint 404s;
and `users.nudge_email_enabled` defaults to false for every existing and new
account. A deploy that skips this document mails nobody, which is the correct
failure mode.

## What gets sent

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

## 3. Check who *would* be mailed

`dry_run` resolves every signal and renders nothing, so it's safe against
production before a single email goes out:

```bash
curl -X POST \
  -H "X-Cron-Secret: $CRON_SECRET" \
  "https://runcoach.fly.dev/api/notifications/run?dry_run=true"
```

```json
{"ok": true, "dry_run": true, "candidates": 1, "nudged": 1, "delivered": 0,
 "skipped_rate_limited": 0, "skipped_repeat": 0, "skipped_no_signal": 0,
 "failed": 0}
```

`delivered` is the only number that means an email left the building. If
`nudged > 0` but `delivered` stays 0 on a real (non-dry) run, SMTP is
misconfigured — check the logs for `SMTP not configured` or a send failure.

## 4. Wire the schedule

**The cron machine must be separate from the web machine.** `fly.toml` sets
`auto_stop_machines = 'stop'`, so the web machine is asleep most of the day and
an in-process scheduler would only fire while somebody happened to be browsing
— which defeats the entire point.

Any external scheduler works, since the trigger is one authenticated HTTP call.
Once a day is plenty; the guards are measured in days.

Using GitHub Actions:

```yaml
# .github/workflows/nudges.yml
name: Outbound nudges
on:
  schedule:
    - cron: '0 15 * * *'   # 08:00 America/Los_Angeles
  workflow_dispatch:
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - run: |
          curl -sSf -X POST \
            -H "X-Cron-Secret: ${{ secrets.CRON_SECRET }}" \
            https://runcoach.fly.dev/api/notifications/run
```

Or a dedicated Fly machine, if you'd rather not depend on GitHub:

```bash
fly machine run alpine \
  --schedule daily \
  --region sjc \
  --app runcoach \
  --env CRON_SECRET="$CRON_SECRET" \
  -- sh -c 'apk add --no-cache curl >/dev/null &&
      curl -sSf -X POST -H "X-Cron-Secret: $CRON_SECRET" \
      https://runcoach.fly.dev/api/notifications/run'
```

The endpoint is safe to call more often than needed: the stored rate limit and
signature mean a second run minutes later sends nothing.

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
| Which guard fires, and the email copy (pure) | `app/core/coaching/outbound_nudge.py` |
| Candidate selection, signals, rate limit, unsubscribe tokens | `app/application/outbound_nudge_service.py` |
| Mailer port | `app/domain/notifications.py` |
| SMTP adapter + the null mailer that refuses | `app/infrastructure/notifications/mailer.py` |
| Trigger + unsubscribe endpoints | `app/web/routers/notifications.py` |
| Consent toggle | `app/web/templates/components/nav.html`, `app/web/static/js/nav.js` |
| Tests | `tests/test_core/test_outbound_nudge.py`, `tests/test_services/test_outbound_nudge_service.py`, `tests/test_routers/test_notifications_router.py` |
