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
| `OPENAI_API_KEY` | AI question generator / validator |
| `ANTHROPIC_API_KEY` | AI question generator |
| `GITHUB_TOKEN` | Pushing question, report and usage data back to GitHub |

To sign session cookies with a stable key, add a `SECRET_KEY` secret and append
`SECRET_KEY=SECRET_KEY:latest` to `--set-secrets`.

## A deploy resets live games

`cloudbuild.yaml` pins the service to one instance (`--min-instances=1
--max-instances=1`, plus `--session-affinity`) because game rooms live in the
instance's memory and local disk. Every deploy creates a new revision (a fresh
container), so **any game in progress ends when a deploy goes live**. Push code
changes when no one is playing.

## Data pushes must not trigger deploys

The running app commits data to GitHub on its own (commit messages ending in
`[skip ci]`): question edits (`contents/questions/`), reports
(`questionmanagement/reported_questions/`) and usage counts (`datastore/usage/`).
Cloud Build skips commits marked `[skip ci]`, so those pushes don't redeploy and
end games. As a backup, the trigger can also ignore these paths. In the console:
**Cloud Build → Triggers → edit the trigger → Ignored files filter**, add:

```
contents/questions/**
questionmanagement/reported_questions/**
datastore/usage/**
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
