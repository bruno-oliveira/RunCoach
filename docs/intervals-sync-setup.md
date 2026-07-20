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
