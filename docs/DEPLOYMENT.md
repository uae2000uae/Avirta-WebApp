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

To sign session cookies with a stable key, add a `SECRET_KEY` secret and append
`SECRET_KEY=SECRET_KEY:latest` to `--set-secrets`.

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

## A deploy resets live games

`cloudbuild.yaml` pins the service to one instance (`--min-instances=1
--max-instances=1`, plus `--session-affinity`) because game rooms live in the
instance's memory and local disk. Every deploy creates a new revision (a fresh
container), so **any game in progress ends when a deploy goes live**. Push code
changes when no one is playing.

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

## Future: deploys without dropping games

Move game rooms to Firestore (see `datastore/firestore_backend.py`, and
[STATE_MIGRATION_SCOPE.md](STATE_MIGRATION_SCOPE.md)) or Redis, and make the
client retry on a transient "room not found". Then the single-instance pin in
`cloudbuild.yaml` can be removed.
