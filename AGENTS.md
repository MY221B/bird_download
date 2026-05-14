## Learned User Preferences

- Never use rm -rf

## Learned Workspace Facts

## Cursor Cloud specific instructions

### Overview
This is a bird photography pipeline (Python scripts) + quiz frontend (React/Vite submodule). The update script handles: `git submodule update --init --recursive`, `pip install -r requirements.txt`, and `npm ci --prefix feather-flash-quiz`.

### Running the Weekly Update scripts
- V1: `bash tools/weekly_refresh_and_push.sh` (calls `tools/run_weekly_refresh.py`)
- V2: `bash tools/v2_weekly_refresh_and_push.sh` (calls `tools/run_weekly_refresh_v2.py`)
- Both require `EBIRD_TOKEN` env var and Cloudinary credentials (`.cloudinary_secrets` file or `CLOUDINARY_CLOUD_NAME`/`CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET` env vars).
- The scripts also run `node feather-flash-quiz/scripts/generate-location-birds-manifest.js` — this requires the submodule to be checked out and npm dependencies installed.

### Frontend (feather-flash-quiz)
- Dev server: `npm run dev --prefix feather-flash-quiz`
- Build: `npm run build --prefix feather-flash-quiz`
- Lint: `npm run lint --prefix feather-flash-quiz` (if configured)

### Python pipeline scripts
- All scripts live in `tools/`. Run with `python3 tools/<script>.py`.
- Key dependencies: `requests`, `pycryptodome` (AES/RSA for BirdReport.cn API), `cloudinary`.

### Gotchas
- `feather-flash-quiz/` is a git submodule. Do NOT run git commands inside it without first confirming `.git` exists there (see README warning).
- `pip install` defaults to `--user` in this environment since system site-packages is read-only. Packages install to `~/.local/lib/python3.12/site-packages/` and are importable without extra config.
- The `城市记录抓取/` directory contains a standalone city report scraper that shares the same Python deps.