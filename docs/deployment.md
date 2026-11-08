# Deployment guide

GridCast is intentionally deployed as two services: a Next.js dashboard on
Vercel at `https://gridcast.rjbassig.dev`, and a Python API at
`https://api.gridcast.rjbassig.dev`. No service is created or deployed by this
repository. The following is the reviewed deployment runbook.

## Public mode and its boundary

For the first public release, use **historical replay mode**:

- `GRIDCAST_REPLAY_ONLY=true` keeps real, precomputed historical observations,
  comparisons, replay series, provenance and the research report available.
- It returns HTTP 503 for the artifact-backed `forecast` and `scenario` routes.
  This avoids running continuous model inference or publishing model checkpoints.
- It never substitutes synthetic observations. A missing release bundle leaves
  the API not ready rather than inventing data.

The API reads paths relative to `GRIDCAST_CONFIG`. Build the compact ignored
bundle locally after validating the exact research snapshot:

```bash
./scripts/python.sh scripts/package_public_release.py
tar -C release -czf gridcast-replay-release.tar.gz gridcast-replay
shasum -a 256 gridcast-replay-release.tar.gz
```

Keep this archive in private object storage or upload it to the backend's
persistent volume. It contains processed observations and derived evaluation
outputs, not raw download archives, checkpoints or credentials. Record the
checksum with the deployed release. Do not commit `release/`.

## 1. Publish the repository first

```bash
git status
git add .
git commit -m "Prepare public GridCast release"
git remote add origin https://github.com/rjbassig/gridcast.git
git branch -M main
git push -u origin main
```

Before `git add`, confirm the checks in [pre-publish checks](#pre-publish-checks)
are clean. If an `origin` remote already exists, use `git remote set-url origin …`
instead of adding it.

## 2. Deploy the dashboard on Vercel

1. In Vercel, import `rjbassig/gridcast`.
2. Set **Root Directory** to `dashboard` and keep the detected Next.js build
   settings (`npm run build`; Vercel installs from `dashboard/package-lock.json`).
3. Add the environment variable below for Production, Preview, and Development
   as appropriate. It is used by the server-side rewrite only and is never
   exposed as `NEXT_PUBLIC_*`.

   ```text
   GRIDCAST_API_URL=https://api.gridcast.rjbassig.dev
   ```

4. Deploy. Confirm `/api/overview` on the Vercel domain returns the backend data.
5. In **Project → Settings → Domains**, add `gridcast.rjbassig.dev`. Vercel will
   show the exact DNS target required for this project.

## 3. Deploy the API on Railway

Railway is a practical low-operations host for the small read-only FastAPI
service. `railway.toml` supplies the Railpack build and Uvicorn health check.
Its cost and free-tier terms change, so check the current plan before enabling a
paid service. Render/Fly.io with a persistent volume are equivalent alternatives.

1. Create a Railway project from the same GitHub repository.
2. Attach a persistent volume and mount it at `/app/release`.
3. Extract the reviewed `gridcast-replay-release.tar.gz` so the mounted path is
   `/app/release/gridcast-replay/...`. Use Railway's volume shell or its
   documented upload path; verify the stored SHA-256 before extraction.
4. Add these Railway variables:

   ```text
   GRIDCAST_CONFIG=/app/release/gridcast-replay/configs/default.yaml
   GRIDCAST_REPLAY_ONLY=true
   GRIDCAST_CORS_ORIGINS=https://gridcast.rjbassig.dev,https://rjbassig.dev
   ```

5. Deploy from `main`, then verify:

   ```bash
   curl -fsS https://YOUR-RAILWAY-DOMAIN/health
   curl -fsS 'https://YOUR-RAILWAY-DOMAIN/api/replay?target=demand&horizon=24' > /dev/null
   ```

6. In Railway's domain settings, add `api.gridcast.rjbassig.dev` and copy the
   exact CNAME target it displays.

The default Railway start command installs the full research environment. That
preserves the option to run a private inference deployment later. The public
replay mode is the lower-cost initial architecture because it needs no scheduled
retraining, GPU, checkpoint volume, or always-on inference traffic.

## 4. Point Namecheap DNS at the two hosts

In **Namecheap → Domain List → rjbassig.dev → Advanced DNS**, add only the
records requested by each host:

| Type | Host | Value | TTL |
|---|---|---|---|
| CNAME | `gridcast` | the exact Vercel target shown for `gridcast.rjbassig.dev` | Automatic |
| CNAME | `api.gridcast` | the exact Railway target shown for `api.gridcast.rjbassig.dev` | Automatic |

Do not create competing A/AAAA/CNAME records for either host. Wait for the
providers to verify DNS and issue TLS certificates, then redeploy Vercel after
the API custom domain is live. Test the public dashboard, `/health`, and a
browser request from `https://gridcast.rjbassig.dev`.

## Local development

Copy the examples, then run the API and dashboard in separate terminals:

```bash
cp .env.example .env
cp dashboard/.env.example dashboard/.env.local
source .venv/bin/activate
set -a && source .env && set +a
./scripts/python.sh -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```bash
npm run dev --prefix dashboard
```

The dashboard proxies browser `/api/*` calls to `GRIDCAST_API_URL`; no localhost
address is hardcoded into client code. Restart Next.js after changing its env
file and restart FastAPI after changing its env file.

## Pre-publish checks

```bash
git status --short
git ls-files | rg '(^|/)(\.env|node_modules|\.next|\.venv|data/(raw|interim|processed)|artifacts)/' && exit 1 || true
git ls-files | rg '\.(parquet|pt|pth|ckpt|zip)$' && exit 1 || true
rg -n --hidden --glob '!.git/**' --glob '!dashboard/node_modules/**' \
  '(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})' . && exit 1 || true
./scripts/python.sh -m pytest -q
ruff check src api tests scripts
GRIDCAST_API_URL=http://127.0.0.1:8000 npm run typecheck --prefix dashboard
GRIDCAST_API_URL=http://127.0.0.1:8000 npm run build --prefix dashboard
```

Run `npm audit --prefix dashboard --omit=dev` before publishing and address any
production dependency finding according to the package maintainer's advisory.
The project has no credential requirement for CAISO acquisition; keep future
hosting credentials in provider variables, never in Git or the dashboard.
