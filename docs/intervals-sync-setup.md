# Intervals.icu Activity Sync Setup

RunCoach uses Intervals.icu as an approved bridge for activities recorded on
Garmin and other supported devices. Users authorize RunCoach once with OAuth;
RunCoach stores the bearer token encrypted and never receives their Intervals.icu
or Garmin password.

## 1. Register The RunCoach OAuth App

Email `david@intervals.icu` with:

- App name: `RunCoach`
- Description: personalized running plans and adaptive coaching based on the
  athlete's own completed runs
- Website: `https://runcoach.fly.dev`
- Logo: `https://runcoach.fly.dev/static/runcoach-logo.svg`
- Privacy policy: `https://runcoach.fly.dev/privacy`
- Production redirect URI:
  `https://runcoach.fly.dev/api/intervals/callback`
- Development redirect URI:
  `http://localhost:8000/api/intervals/callback`
- The owner's Intervals.icu athlete ID, shown at the bottom of the Intervals.icu
  settings page

Intervals.icu initially makes an OAuth app available only to its owner. Ask them
to publish it after private testing if other RunCoach users should connect.

## 2. Configure RunCoach

Set these locally in `.env`:

```text
INTERVALS_CLIENT_ID=<issued client id>
INTERVALS_CLIENT_SECRET=<issued client secret>
INTERVALS_REDIRECT_URI=http://localhost:8000/api/intervals/callback
INTERVALS_INITIAL_SYNC_DAYS=365
```

Set the production secrets and deploy:

```bash
fly secrets set \
  INTERVALS_CLIENT_ID=<issued-client-id> \
  INTERVALS_CLIENT_SECRET=<issued-client-secret> \
  INTERVALS_REDIRECT_URI=https://runcoach.fly.dev/api/intervals/callback \
  --app runcoach
fly deploy
```

The deployment runs Alembic migration `022_add_intervals_sync` automatically.

## 3. Connect Garmin To Intervals.icu

Each athlete must:

1. Create a free Intervals.icu account.
2. Open Intervals.icu Settings, then Integrations.
3. Connect Garmin and authorize activity downloads.
4. Sync the Garmin device with Garmin Connect and confirm the run appears in
   Intervals.icu.
5. In RunCoach, select **Connect activities** and approve `ACTIVITY:READ`.

RunCoach automatically imports the previous year after OAuth completes. Later,
the athlete selects **Sync new runs** after a workout. The OAuth authorization is
persistent, so no further Intervals.icu login is required unless access is
revoked.

## Limitations

- Intervals.icu does not expose Strava-sourced activity details through its API.
  Connect Garmin or another original activity source directly to Intervals.icu.
- Garmin generally forwards activities recorded on Garmin devices, not files
  uploaded to Garmin by another third party.
- Automatic per-workout webhooks are not enabled yet; manual sync is one click.

## Live import (webhook)

Without a webhook, new activities arrive on the daily sweep or when the runner
presses sync. With one, a run reaches the plan a minute or two after the watch
uploads it: import → wellness → adapt → re-mirror → one push notification.

1. Pick a long random secret and set it on the app:
   `fly secrets set INTERVALS_WEBHOOK_SECRET=...`
2. In Intervals.icu → Settings → your app → **Manage App**, set the webhook URL
   to `https://<your-host>/api/intervals/webhook`, paste the same secret, and
   subscribe to `ACTIVITY_UPLOADED` and `ACTIVITY_ANALYZED` (optionally
   `SPORT_SETTINGS_UPDATED`, which refreshes HR anchors).
3. Check it: the endpoint answers `404` while the secret is unset, `403` for a
   wrong secret, and `{"ok": true, "accepted": N}` for a real delivery. The
   work runs after the response; look for `Intervals webhook for user …` in the
   logs.

Intervals does not deliver activity webhooks for activities it pulled from
Strava — those still arrive on the daily sweep.

## Wellness scope

RunCoach now requests `ACTIVITY:READ,WELLNESS:READ,CALENDAR:WRITE`. Wellness
(overnight HRV, resting HR, sleep) pre-fills the morning check-in and stands in
for it when the runner doesn't check in. Connections made before this change
keep working for activities and the watch mirror; the first wellness call
403s, the grant is recorded as legacy, and the check-in card offers a one-tap
reconnect.
