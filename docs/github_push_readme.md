# GitHub Push Integration (Admin and Auto Snapshot)

This project includes a built-in GitHub integration that pushes question, report and usage data back to the repository.

What exists:
- Admin page action: Push or Sync all contents/questions/*.json files to your repository
- Automatic pushes: question edits, reported questions and per-instance usage counts (`datastore/usage/`) are pushed by the app with `[skip ci]` so they don't trigger a deploy

Configuration
1) Secrets (no token stored in settings):
   - Create a GitHub Personal Access Token (classic with `repo` scope, or fine‑grained with Contents: Read & write for your repo).
   - In Google Secret Manager, store the token under secret name `GITHUB_TOKEN` and map it to the environment variable `GITHUB_TOKEN` during deploy (see `cloudbuild.yaml`).
2) Open Admin Controls → API Settings and fill in only:
   - github_repo_owner: e.g., uae2000uae
   - github_repo_name: e.g., Avirta-1
   - github_branch: e.g., Avirta-1 (defaults to main)
3) Save settings.

Admin Push (manual)
- Navigate to /push_questions_to_github (Admin only)
- Choose Push All or Sync
- The service uses GitHub contents API to create/update files.

Notes
- If GitHub settings are missing/invalid, the game still ends; a notice is flashed and an event is logged.
- For public repositories, consider excluding sensitive data before sharing.
- The integration relies on the GitHub REST v3 contents API.
