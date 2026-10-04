# Private-server release gates

Target confirmed by the owner: a closed company server, local inference, English documents.
Status: **not production-released**. `DEPLOYMENT_MODE=production` enables startup checks;
it is not certification and does not make the remaining gates pass.

## Implemented in the current hardening pass

- Parser admission reserves capacity before reading the request body; at most one upload/extraction owns the slot.
- A 30-second incoming transfer deadline and the existing 20 MB byte limit bound input.
- Client cancellation leaves the running extraction holding its slot until it finishes.
- Parser readiness checks the installed English OCR language, independently of liveness.
- Credential records support `expires_at` (timezone required) and boolean `disabled`.
  Expired/disabled/malformed matched records fail with the same 401. Legacy records remain
  usable only in development. Production rejects synthetic providers, invalid encryption
  keys, malformed registries, missing expiry and configurations with no active credentials.
- The registry remains environment-based. Changes require recreating/restarting API,
  worker and dispatcher services; this is not immediate revocation or corporate SSO.
- Docker context excludes nested Python bytecode, avoiding host-generated test caches.
- Inner ring OCR retries isolated overlapping windows with padding and upsampling.
  Labels are deduplicated by case/whitespace only; letters and digits are not guessed.
  User-host Linux CheckOCR passed all 7 tests on 2026-10-02; this is fixture evidence,
  not validation of arbitrary documents.
- Parser capacity responses defer jobs without consuming extraction attempts. The existing
  30-second outbox redispatch delay prevents immediate polling loops. Lease fencing remains
  mandatory; actual extraction failures retain their bounded failure policy.

## Required gates before customer documents

| Gate | Required evidence | Current status |
|---|---|---|
| Linux image | Full Docker suite, including native OCR, PostgreSQL FORCE RLS and Redis recovery | User CheckOCR: 7 passed; full suite with the latest hardening changes pending |
| Held-out parsing corpus | Independent English PDFs: prose, two columns, scanned/ruled/borderless tables, figures, rotations, skew and low resolution | NIST fixture alone is insufficient; broader corpus not yet validated |
| Critical data | Exact reviewed values for numbers, units and category/cell associations; missing labels and failures remain visible | Human review required; no universal accuracy claim |
| Inference quality | Paired real-model runs with answer/evidence review, failures and latency included | Synthetic demo is not acceptable release evidence |
| Identity | Company identity integration or an explicitly accepted service-credential policy, expiry and revocation procedure | Expiry/disable mechanics implemented; SSO and policy pending |
| Network | Approved TLS ingress, company CA/certificates, private service access, tested egress policy | Local loopback HTTP demo remains; no server deployment performed |
| Keys/storage | Secret provisioning/rotation, encrypted host disks and backups, restricted operator access | Application encryption implemented; operating procedures not validated |
| Recovery | Isolated restore drill including DB, blobs and encryption key; queue crash/recovery test | No verified restore drill |
| Capacity | Load test on target CPU/GPU/disk; queue wait, per-stage p95, memory and failure rate | OCR-first is the supported laptop profile; Qwen2.5-VL 3B measured at 0.4 output tokens/s with invalid output, so vision is not a production dependency |
| Operations | Alert routing, runbooks, retention/deletion, patching and dependency/image scans | Metrics and local dashboards present; external alerts and scans pending |
| Security review | Tenant/adversarial tests and independent review of actual deployment | No production security sign-off |

## Configuration and verification

Do not change existing `.env` or credentials automatically. To opt into startup guards,
operators set `DEPLOYMENT_MODE=production`, `PROVIDER_MODE=ollama`, a valid 32-byte
base64 encryption key, and a hashed credential registry. Each record includes a UTC
expiry such as `"expires_at":"2027-01-01T00:00:00Z"`; choose a real policy, not this example.
Use `"disabled":true` to disable a record, then recreate affected services. Provision and
verify local generation/embedding models before switching providers.

From the repository directory, `./scripts/docker.ps1 CheckOCR` verifies public-fixture OCR.
`./scripts/docker.ps1 Test` runs the full isolated test stack; it must not target production data.
Keep the existing vision/GPU overrides when rebuilding the application.

Unresolved release gates are blockers, not features completed by documentation. The current
parser remains heuristic and review-assisted; it must not be sold as automatic understanding
of arbitrary heterogeneous documents.
