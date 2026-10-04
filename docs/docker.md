# Docker and operations

## Lifecycle

Use Python 3.13 and `uv sync --frozen`. `.venv` is managed by the user. Run `scripts/setup.py` only once; it writes random local secrets and alpha/beta credentials without printing them. Existing files are preserved.

```powershell
./scripts/docker.ps1 Up -Workers 2
./scripts/docker.ps1 Verify
./scripts/docker.ps1 Test
./scripts/docker.ps1 Down
```

Services: Nginx gateway, PostgreSQL+pgvector, Redis, migration job, API, dispatcher, worker replicas, isolated parser, Streamlit, Prometheus and Grafana. Optional `local-models` profile adds Ollama; `tests` adds a separate ephemeral test database and test runner. The gateway publishes API 8003, UI 8503, Grafana 3003 and Prometheus 9093 only on IPv4 loopback. PostgreSQL and Redis have no host ports.

Only the gateway joins the ordinary `frontend` bridge. It forwards to fixed application targets on the internal `ingress` network. Application services retain internal-only networks; the gateway has no database credentials, blob mounts or membership of `private`/`parser_net`. WebSocket upgrades are supported, request/response proxy buffering is disabled, and request access logs are disabled. The proxy accepts up to 21 MiB to accommodate UI multipart overhead; the API independently enforces its document cap.

If containers are healthy but port publication is missing, publishing directly from internal-only networks can be the cause. This project now publishes through `gateway`, so inspect `docker compose port gateway 8003` and `docker compose port gateway 8503`. Apply the change with `./scripts/docker.ps1 Up -Workers 2`, then `./scripts/docker.ps1 Verify`. Recreating only API/UI does not start the gateway. Do not remove volumes or turn off internal isolation. See the [matching Docker/Moby report](https://github.com/moby/moby/discussions/53256).

Readiness: database -> migrations -> API -> dispatcher/workers/UI; Redis and parser have separate health checks. Application filesystems are read-only, with limited temporary storage and non-root processes. Worker/parser CPU/memory/PID limits are explicit. Log rotation is 20 MB x 5.

## Horizontal consumers

Optional visual extraction setup and GPU provisioning are documented in [PDF extraction](ingestion.md). Use `DownloadVision` once, then `Up -Vision -Gpu`; the model runtime stays on an internal network. In this single-slot parser build, submit visual documents sequentially: concurrent long model jobs can exhaust the existing bounded parser-busy retries. More workers do not add GPU capacity.

```powershell
docker compose up -d --scale worker=3
```

Do not set container_name or a fixed published worker metrics port. Prometheus DNS discovery scrapes each worker. Shared blob storage must be reachable by every consumer; the named volume supports one host only. The parser/model may bottleneck before more consumers improve throughput. Observe queue age, stage p95 and CPU/memory before increasing replicas.

## Recovery

If the gateway restarts, inspect `docker compose logs --tail 50 gateway` first. Validate its configuration under the actual non-root/read-only settings with `docker compose run --rm --no-deps gateway -t`. All five Nginx temporary paths must use the writable `/tmp` tmpfs, including the unused FastCGI/uWSGI/SCGI module paths. After a configuration edit, use `docker compose restart gateway`, then run Verify. A missing published port while the gateway is restarting is a secondary symptom.

- Redis unavailable: job is already durable in PostgreSQL; dispatcher retries publishing. Authenticated API requests fail closed if the rate limiter is unavailable.
- Worker crash: lease expires; message is reclaimed or redispatched. A stale worker cannot finalize a new owner's task.
- Repeated crash: after three attempts, the job becomes dead and is visible in the UI; inspect metadata-only logs before resubmission.
- PDF parse rejection: unsupported/encrypted/oversized/active or badly formed PDF is not indexed. Do not bypass checks for convenience.
- Parser busy/temporary transport failure: bounded retry; no silent infinite loop.
- Encryption key lost: encrypted content is unrecoverable. Preserve the key separately from data backups.
- Upload interruption: partial upload is removed when the request exits normally. Host crashes can leave encrypted orphan objects; scheduled orphan reconciliation is still a production requirement.

An 'access denied' Docker named-pipe error from an agent is not proof the engine is stopped. This build session could validate Compose but could not access the Docker engine. Run the provided verification/test commands in the user's PowerShell session.

## Backups and deletion

Back up PostgreSQL, encrypted blob volume and encryption key as one recovery set. Keep application runtime and migration credentials separate. Document deletion cascades through chunks/jobs and purges tenant embedding reuse; encrypted source deletion follows database deletion. This is not an atomic cross-storage transaction. Account for orphans and backup retention before promising data erasure.

`Down` does not remove volumes. Never run destructive volume deletion as troubleshooting. A production restore runbook and tested restore drill remain required.

## Monitoring

Grafana provisions its datasource and dashboard automatically. Read `docs/logging.md` for metrics/logs. Prometheus rule evaluation works locally; no Alertmanager or external notification channel is configured. Rotate Grafana, DB and Redis passwords before deployment. Secrets in the local `.env` are for the portfolio environment; use a deployment secret manager later.
