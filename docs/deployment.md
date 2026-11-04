# Local execution and practical deployment

## Local

Use Python 3.11+ (tested Python 3.13) and Node 22+ (tested Node 24). Create a virtualenv, install `.[dev,deep]`, then use the commands in README. On macOS XGBoost/LightGBM require OpenMP. A standard installation is `brew install libomp`; alternatively `scripts/python.sh` discovers the installed PyTorch OpenMP library without modifying system directories.

Run API and Next.js in separate terminals. API binds `127.0.0.1:8000`, dashboard binds `127.0.0.1:3000`. The frontend proxies `/api` requests to FastAPI, so no browser key, model-file access or permissive CORS is needed. Set server-only `GRIDCAST_API_URL` when deploying processes separately.

The current local verified build is not public. Do not deploy this research API to an untrusted network as an authenticated multi-tenant service.

## Low-cost public demonstration strategy (not executed)

A small single-host Linux deployment can run a read-only release snapshot with Uvicorn behind a TLS reverse proxy and a Next.js process. Mount the processed Parquet, trusted artifacts and verified results read-only; raw ZIPs need not be served. Bind FastAPI privately. Add rate limiting, bounded request timeouts, authentication as needed, resource limits, dependency scanning and artifact checksum verification before exposure. Budget costs separately; no paid services or cloud resources were created.

For a public portfolio, a read-only replay snapshot is preferable to implying a live grid service. Preserve the visible historical label, timestamps and limitations. Static frontend-only hosting cannot execute Python/torch models; it is insufficient for the implemented scenario endpoint.

## Updates and model promotion

No scheduled jobs or live retraining were installed. To refresh research data, change the experiment window intentionally, run ingestion/prepare/training/tests/report into an isolated release directory, review metrics and provenance, then atomically switch the application to the new immutable snapshot and restart caches. Ingestion skips successful checksummed chunks; a partially failed acquisition can resume. Dataset updates must not occur concurrently with prepare/train; run pipeline stages sequentially.

Do not keep changing parameters and quoting the same H2 2025 period as an untouched test. Future model-development iterations require a new prospective holdout or explicit exploratory labeling. The present final results can no longer serve as unseen development feedback.

For scheduled research later, use macOS launchd or cron to run a lock-protected acquisition job. Add atomic staging, alert delivery and reviewed promotion before scheduling automatic replacement. No live-service readiness, failover, auth, trading integration or automated drift threshold has been validated.
