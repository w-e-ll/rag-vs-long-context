# Security model and limits

Assumption: multi-user service handling confidential PDFs; users within a tenant currently share document access. Tenants are mutually untrusted. Platform operators, application processes, database administration and the host remain trusted.

## Implemented boundaries

| Boundary | Control | Remaining limit |
|---|---|---|
| Identity | Random opaque credentials; SHA-256 hashes mapped to tenant/user/role; expiry and disabled flags; production requires expiring credentials | Static registry; changes require service recreation/restart; no corporate SSO or self-service rotation |
| Tenant access | UUID IDs, explicit tenant SQL predicates, composite FKs, transaction-local FORCE RLS, identical not-found responses | Shared app role can set tenant context; a compromised backend is outside this boundary |
| Upload | application/pdf, signature check, 20 MB actual streamed-byte cap, random paths, authenticated encrypted frames | Streamlit buffers a bounded upload; upstream TLS/connection rate controls still needed |
| Load | Shared Redis fixed-window 120 requests/minute/tenant; DB admission limit of 20 pending tasks | Fixed-window bursts and all-platform capacity must be sized; no fair-scheduling SLA |
| Parsing | Isolated non-root service/subprocess, internal network, no keys/mounts, Linux/container limits, timeout, active-content restrictions | Not a malware scanner or full CDR system; parser libraries require patching |
| OCR | Local Tesseract, no cloud OCR; confidence limitations displayed and manual review required | English only; handwriting, skew, low resolution and complex tables are not reliably solved |
| Content | Document text treated as untrusted data; no agent tools, URL fetching or code execution; output shown as text | Prompt instructions cannot guarantee injection resistance; manual review is not proof of safety |
| Storage | Tenant-derived AES-GCM for raw PDFs, extracted text, chunks, questions and answers | Vectors, hashes, status metadata and IDs remain readable to DB administrators; encrypt disks/backups |
| Queue | Only IDs in Redis, Redis password, internal-only service, idempotent jobs and lease-fenced commits | Redis ACL users and TLS are deployment hardening work; shared credentials trust service processes |
| Inference | Demo or internal-network private Ollama only; no hosted provider adapter; LangSmith tracing explicitly disabled | Host/private model deployment must be trusted and audited; no claim of secure model output |
| Logs / metrics | Allowlisted events, stack frames without messages/locals; bounded metric labels; no content/tenant labels in Prometheus | Operator dashboards are cross-tenant aggregate views; audit retention/immutability is not implemented |
| Deletion | Delete document + cascading jobs/chunks; delete encrypted source; conservative tenant embedding-cache purge | DB/object deletion is not atomic; orphan cleanup, backup expiry and secure-erasure policy remain |

## Before real confidential deployment

PDF v2 optionally connects the parser to a dedicated internal `vision_net` for local structured image extraction. This is an additional trusted model process, with no application secrets or document storage mounts. The endpoint is fixed in code; no redirects, proxy environment or client-provided URL is accepted. Model responses are bounded and schema-validated, remain untrusted evidence, and cannot invoke tools. Public model weights are provisioned through a separate one-off downloader with no access to document networks or volumes. Runtime document processing retains internal-only networking. See docs/ingestion.md.

Local ingress uses a non-root Nginx gateway with loopback-only host ports and fixed upstreams. Only this gateway joins a non-internal bridge; application services retain internal-only networks. The gateway can see proxied plaintext and is a trusted component with possible outbound connectivity; its compromise is outside the tenant isolation guarantee. It has no application secrets or blob mounts and cannot directly reach database/parser networks. Request access logs and proxy buffering are disabled. Internal Docker networks are not a substitute for production firewall/egress policy, DNS controls or TLS. Prometheus is unauthenticated and operator-local; never publish these ports to a public interface unchanged.

Use federated identity with validated issuer/audience/expiry and server-owned memberships. Decide if all tenant members may read all tenant documents; otherwise add resource ACLs to retrieval and parent expansion too. Replace local shared volume with a policy-controlled object store for multi-host deployment. Use KMS/envelope key rotation and separate service identities. Enforce TLS at ingress and service boundaries. Add malware/CDR handling, an audited retention/deletion workflow, orphan reconciliation, backup encryption and a restore drill. Run dependency/image scanning and adversarial tenant/queue/parser tests in the target environment. Do not claim compliance or production readiness from these local tests.

The service does not accept arbitrary URLs, model endpoints, tenant IDs or executable loader configurations from clients. No cloud account, hosted tracing or paid provider was used during this build.

Sources: [OWASP file upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html), [OWASP prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html), [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
