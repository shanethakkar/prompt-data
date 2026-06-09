# Deploy runbook — Prompt Data

Frontend on **Vercel**, backend on **Render**, connected so `/ask` works end to end. The repo is
already deploy-ready: slim DB committed as `data/demo.db.gz`, `Dockerfile` + `render.yaml` for the
backend, env-driven CORS, and a rate/spend guard on `/ask`. The steps below are the account/dashboard
work that can't be scripted from here.

Order matters: push to GitHub, deploy the backend, deploy the frontend, then connect the two origins.

## 0. Push to GitHub (one time)
```bash
git remote add origin https://github.com/shanethakkar/prompt-data.git
git push -u origin main
```
The push includes `data/demo.db.gz` (~51 MB). If the remote already has commits, reconcile first.

## 1. Backend on Render
1. Render dashboard -> **New + > Blueprint** -> connect `github.com/shanethakkar/prompt-data`.
   Render reads `render.yaml` and proposes the `prompt-data-api` web service (Docker).
2. Set the two secret env vars (marked `sync:false`):
   - `ANTHROPIC_API_KEY` = your key.
   - `CORS_ORIGINS` = your Vercel URL (you'll get it in step 2; you can set a placeholder now and
     update after, e.g. `https://prompt-data.vercel.app`).
3. Deploy. The build decompresses the slim DB into the image and starts uvicorn on `$PORT`.
4. Copy the service URL, e.g. `https://prompt-data-api.onrender.com`. Verify:
   `curl https://prompt-data-api.onrender.com/health` -> `{"status":"ok",...}`.
   - Free plan sleeps after ~15 min idle (~50s cold start on the next request). Bump `plan: starter`
     in `render.yaml` (or the dashboard) for always-on.

## 2. Frontend on Vercel
1. Vercel -> **Add New > Project** -> import the same GitHub repo.
2. **Root Directory = `frontend`** (important — it's a monorepo). Framework auto-detects as Next.js.
3. Add env var `NEXT_PUBLIC_API_BASE` = the Render URL from step 1 (no trailing slash, no `/api`).
4. Deploy. Copy the site URL, e.g. `https://prompt-data.vercel.app`.

## 3. Connect the origins
1. In Render, set `CORS_ORIGINS` to the exact Vercel URL from step 2 and redeploy (or save env -> it
   redeploys). The browser calls the backend directly, so this must match.
2. Smoke-test the live site:
   - A clear question ("How many orders were delivered?") -> streams stages -> answer card.
   - An ambiguous one ("Who are the top sellers?") -> clarification chips.
   - `/evals`, `/gallery`, `/methodology`, `/limitations` render (static; work even if the backend is asleep).

## Notes
- **Spend guard:** `/ask` is limited to `RATE_LIMIT_PER_MINUTE` (5) per IP and `DAILY_REQUEST_CAP`
  (500) total per day; over the limit returns HTTP 429 with a friendly message. Tune in Render env.
- **demo.db:** the live DB is the slim build — no `geolocation` table and no review free-text columns.
  Those questions won't work in the demo (noted on `/limitations`); all showcased questions do.
  To refresh it: `make load-db && make pack-db`, commit `data/demo.db.gz`, push (Render rebuilds).
- **Cost:** every `/ask` calls Sonnet. The guard caps exposure; watch Anthropic usage after launch.
- **Streaming path:** prod uses direct browser->Render CORS (not the Vercel proxy) to avoid timeouts
  on the long SSE stream. Local dev keeps the Next `/api` rewrite (set `API_BASE`, leave
  `NEXT_PUBLIC_API_BASE` unset).
