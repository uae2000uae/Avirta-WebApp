# Deploying Avirta

Avirta runs on **Google Cloud Run** (service `avirta`, region `us-central1`) and
is deployed only through **Cloud Build**: a push to the `Avirta-1` branch on
GitHub starts the Cloud Build trigger, which runs [`cloudbuild.yaml`](../cloudbuild.yaml).
There are no manual deploy scripts; edit `cloudbuild.yaml` to change how the
service is deployed.

What gets uploaded is controlled by [`.gcloudignore`](../.gcloudignore) (tests,
docs, IDE folders and CI config are excluded; runtime data is kept).

## Secrets

Cloud Run reads these from **Secret Manager** (mapped in `cloudbuild.yaml`
`--set-secrets`):

| Secret | Used for |
|--------|----------|
| `OPENAI_API_KEY` | AI option "ChatGPT (OpenAI)" |
| `ANTHROPIC_API_KEY` | AI option "Claude (Anthropic)" |
| `CUSTOM_AI_API_KEY` | AI option "Your own AI key" (read directly from Secret Manager; not in `--set-secrets`) |
| `GITHUB_TOKEN` | Pushing question, report and usage data back to GitHub |
| `SECRET_KEY` | Signs session cookies, so admin logins survive restarts |
| `ADMIN_PASSWORD_HASH` | Salted hash of the admin password (never the password itself) |

### Admin login

The admin username is `Admin` (override with an `ADMIN_USERNAME` secret). The
password is checked against `ADMIN_PASSWORD_HASH`; if that secret is missing,
admin login is refused. After 5 failed attempts in 15 minutes, that address is
locked out for 15 minutes.

To change the password, create a new hash and add it as a new secret version,
then redeploy (or restart the service):

```bash
python -c "from werkzeug.security import generate_password_hash as g; import getpass; print(g(getpass.getpass('New admin password: '), method='pbkdf2:sha256:600000'), end='')" > hash.txt
gcloud secrets versions add ADMIN_PASSWORD_HASH --project=avirta-461720 --data-file=hash.txt
rm hash.txt
```

### Tests before deploy

`cloudbuild.yaml` runs the whole test suite first (with dummy values in place
of every secret). If any test fails, the build stops and nothing is deployed.

### AI keys

The ChatGPT and Claude keys are managed only in Secret Manager
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`); the admin page shows whether each one is
found but never asks for it. To change one, add a new secret version in the Cloud
Console (Security → Secret Manager); the next revision picks it up.

Only the **Your own AI key** option takes a key on the admin page (**Admin → API
Settings → Save key**), stored as a new version of `CUSTOM_AI_API_KEY`. For that,
the Cloud Run service account needs **Secret Manager Secret Version Adder** on
`CUSTOM_AI_API_KEY`, plus **Secret Manager Admin** the first time (or create the
secret once yourself in the console). When running locally, that key goes to the
untracked file `contents/admin_controls/.local_ai_keys.json` instead.

## Live games survive deploys

Every game room is saved to Firestore (database `avirta-state`, us-central1,
collection `rooms`) after each request that changes it, and a new revision
loads a room from there the first time a player asks for it. So a deploy or an
instance restart no longer ends games in progress: players carry on where they
were. The code is `contents/game_room/room_store.py`; Cloud Run turns it on with
`ROOM_STORE=firestore` and `FIRESTORE_DATABASE=avirta-state` (set in
`cloudbuild.yaml`). Locally and in tests there is no store and rooms stay in
memory, as before.

Rooms untouched for 12 hours are treated as finished, and ending a game deletes
its document. If Firestore is unreachable the game keeps running from memory and
the error is logged.

The service is still pinned to one instance (`--min-instances=1
--max-instances=1`, `--session-affinity`): each instance keeps its own copy of
a room in memory, so two instances serving the same room at once would drift
apart. During the minute a deploy overlaps the old and new revisions, a move
made on the old one after the new one loaded the room can be lost.

The project's `(default)` database is an older, unused Datastore-mode database
in `nam5`; the app does not touch it.

## Syncing app data to GitHub

The running app commits its own data to `Avirta-1` through one sync
(`contents/admin_controls/github_sync.py`):

- **What:** every changed data file - questions, reported questions, usage
  counts (`datastore/usage/`), game logs (`contents/game_events/`), AI batches,
  and admin settings/presets - in one commit. Unchanged files are skipped;
  source code is never pushed from the server, and nothing is deleted on GitHub.
- **When:** the **Sync to GitHub** button (Admin → Question Management), every
  game end or reset, and whenever questions or reports change. Requests made
  while a sync is running are queued, never dropped.
- **Failures:** each sync retries twice. If it still fails, a pop-up appears
  immediately for admins and for the host who ended the game, the admin log
  records it, and Cloud Logging gets an error tagged `GITHUB_SYNC_FAILED`.
  The data stays on the server and goes out with the next successful sync
  (until the instance restarts).
- Needs `GITHUB_TOKEN` (contents: read & write on the repository).

These commits end in `[skip ci]`, which Cloud Build honours, so they never
redeploy and end games. As a backup, the trigger can also ignore these paths.
In the console: **Cloud Build → Triggers → edit the trigger → Ignored files
filter**, add:

```
contents/questions/**
questionmanagement/reported_questions/**
questionmanagement/ai_generated_questions/**
contents/game_events/**
datastore/usage/**
contents/admin_controls/*.json
```

Because the app commits to `Avirta-1` too, run `git pull` before working locally.

## Public access

`--allow-unauthenticated` on the deploy already grants public access; no separate
IAM step is needed (an extra `add-iam-policy-binding` step used to race and fail
with an ETag `ABORTED` error). If access ever has to be granted again:

```bash
gcloud run services add-iam-policy-binding avirta --region=us-central1 --member=allUsers --role=roles/run.invoker
```

## Future: more than one instance

To lift the single-instance pin, make Firestore the source of truth on every
request (read the room at the start, write it with a transaction at the end)
instead of the in-memory copy. See [STATE_MIGRATION_SCOPE.md](STATE_MIGRATION_SCOPE.md).
