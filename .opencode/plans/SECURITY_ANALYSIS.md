# SECURITY_ANALYSIS.md — RunCoach Security Hardening Plan

## Executive Summary

This document catalogs security vulnerabilities, data leakage risks, and privacy concerns identified in the RunCoach FastAPI application, along with prioritized remediation actions at both code and infrastructure levels.

**Severity Distribution:**
- **Critical:** 6 issues
- **High:** 8 issues
- **Medium:** 7 issues
- **Low:** 5 issues

---

## 1. CRITICAL — Authentication & Authorization

### 1.1 Debug Endpoints Expose Sensitive Configuration
**Severity:** Critical
**Files:** `app/main.py:176-204`

**Issue:** When `DEBUG=True`, two endpoints are exposed:
- `/debug/config` — leaks Google Client ID preview, secret key length, and configuration state
- `/debug/test-auth` — generates and previews JWT tokens with payload

**Impact:** In any environment where debug mode is accidentally enabled, an attacker can enumerate secrets, validate JWT signing, and preview token payloads.

**Remediation:**
- Remove `/debug/config` and `/debug/test-auth` endpoints entirely from production code
- Gate debug endpoints behind a separate `ENABLE_DEBUG_ENDPOINTS` env var (default `False`), independent of `DEBUG`
- Add IP allowlisting if debug endpoints must exist in staging

### 1.2 JWT Token Exposed in API Response Body
**Severity:** Critical
**Files:** `app/routers/auth.py:73-76`

**Issue:** The `/api/auth/google` endpoint returns `access_token` in the JSON response body (`Token` schema) in addition to setting it as an httponly cookie.

**Impact:** JWT tokens in response bodies are accessible to JavaScript, vulnerable to XSS exfiltration, and may be logged by browsers, proxies, or monitoring tools.

**Remediation:**
- Remove `access_token` from the JSON response body
- Return only `{"message": "authenticated", "user": {...}}` and rely solely on the httponly cookie
- Update frontend to not expect token in response body

### 1.3 No CSRF Protection on State-Changing Endpoints
**Severity:** Critical
**Files:** `app/main.py`, `app/middleware.py`

**Issue:** The application uses cookie-based authentication (`access_token` cookie with `samesite="lax"`) but has no CSRF token validation. `samesite="lax"` only protects against cross-site top-level navigations, not all CSRF vectors (e.g., `<form>` POST submissions from same-site contexts).

**Impact:** An attacker can craft malicious pages that trigger state-changing actions (delete plans, modify training, save recipes) when the victim is authenticated.

**Remediation:**
- Add CSRF middleware (e.g., `starlette-csrf` or custom implementation)
- Implement double-submit cookie pattern or CSRF token in headers
- Exclude CSRF check for `/api/auth/google` and `/health` endpoints

### 1.4 Strava OAuth Callback Missing Origin/Referer Validation
**Severity:** Critical
**Files:** `app/routers/strava.py:99-167`

**Issue:** The `/api/strava/callback` endpoint accepts any `code` and `state` query parameters without validating the request origin. The `state` parameter is a JWT (good), but there's no check that the callback originated from the legitimate Strava authorization flow.

**Impact:** An attacker could potentially replay or forge callback requests to link a Strava account to a victim's session.

**Remediation:**
- Validate `Origin` or `Referer` header on the callback
- Ensure the JWT `state` token includes an `iat` (issued-at) claim and reject tokens older than 10 minutes
- Add CSRF token to the initial `/api/strava/connect` request

### 1.5 EncryptedString Falls Back to Plaintext for Legacy Values
**Severity:** Critical
**Files:** `app/models/encrypted_type.py:62-66`

**Issue:** When `EncryptedString` encounters a value that doesn't look like a Fernet token (no `gAAAAA` prefix), it returns the plaintext value as-is, logging that it will be re-encrypted on the next write.

**Impact:** If an attacker gains read access to the database, legacy plaintext tokens are immediately readable. The "re-encrypt on next write" never happens if the value is only read.

**Remediation:**
- Add a migration script to re-encrypt all legacy plaintext tokens
- After migration, change behavior to return `None` for any non-Fernet value and log a warning
- Consider implementing key rotation support

### 1.6 Fernet Key Derived from SECRET_KEY via SHA-256 (No Salt)
**Severity:** Critical
**Files:** `app/models/encrypted_type.py:15-18`

**Issue:** The Fernet encryption key is derived deterministically from `SECRET_KEY` using `hashlib.sha256(secret.encode()).digest()` with no salt or KDF.

**Impact:** If `SECRET_KEY` is compromised, all encrypted tokens can be decrypted. There's no defense-in-depth — the same key protects both JWT signing and data encryption.

**Remediation:**
- Introduce a separate `ENCRYPTION_KEY` environment variable
- Use a proper KDF (e.g., HKDF or Argon2) with a stored salt
- Rotate encryption keys periodically with support for decryption under old keys

---

## 2. HIGH — Access Control & Data Leakage

### 2.1 Shared Plan View Leaks Owner PII
**Severity:** High
**Files:** `app/routers/plan_sharing.py:113-125`

**Issue:** The `/shared/{share_token}` endpoint passes the plan owner's full `User` object to the template context (`ctx["plan_owner"] = owner`), which may include email, name, and profile picture URL.

**Impact:** Anyone with a share link can see the plan owner's personal information (email, name, Google profile picture).

**Remediation:**
- Only pass anonymized owner info to the template (e.g., first name only, or "Anonymous Runner")
- Never expose email or `google_id` in shared views
- Audit the `plan_shared.html` template to ensure no PII is rendered

### 2.2 Plan Ownership Check Bypass via `check_ownership=False`
**Severity:** High
**Files:** `app/services/plan_helpers.py:39-81`, `app/routers/plan_sharing.py:141`

**Issue:** The `get_plan_or_404()` function has a `check_ownership=False` parameter. The `save_plan_to_account` endpoint uses this, then performs its own ownership check. However, the check at line 146-148 only verifies if the plan owner has a `google_id` or `email` — if an anonymous user's account was partially set up, this check could be bypassed.

**Impact:** A user could potentially claim a plan that belongs to another anonymous session if the ownership check has edge cases.

**Remediation:**
- Remove `check_ownership=False` parameter; always check ownership
- In `save_plan_to_account`, verify the plan's `user_id` matches the `anonymous_user_id` cookie before allowing claim
- Add explicit assertion that `training_plan.user_id == anonymous_user_id`

### 2.3 RunLog Response Exposes `user_id` to Client
**Severity:** High
**Files:** `app/schemas.py:387-400`

**Issue:** `RunLogResponse` includes `user_id` field, which is returned in all run log API responses (`/api/runs`, `/api/runs/{run_id}`, etc.).

**Impact:** If any endpoint inadvertently returns another user's run data (through a bug or misconfiguration), the `user_id` would be exposed, enabling user enumeration.

**Remediation:**
- Remove `user_id` from `RunLogResponse` schema — the client already knows whose data it's viewing
- Audit all API responses for unnecessary user ID exposure

### 2.4 Google Token Verification Logs Email Address
**Severity:** High
**Files:** `app/services/auth_service.py:78`

**Issue:** `verify_google_token()` logs the user's email at DEBUG level: `f"Google token verified successfully for: {payload.get('email')}"`.

**Impact:** If debug logging is enabled in production, user email addresses are written to logs, which may be accessible to operators, log aggregation services, or attackers who compromise log storage.

**Remediation:**
- Remove email from log messages; use user ID or a truncated/masked identifier
- Ensure production logging level is `INFO` or above
- Add log sanitization middleware to prevent PII in logs

### 2.5 Strava Sync Errors Leak Internal Details
**Severity:** High
**Files:** `app/routers/strava.py:246-249`

**Issue:** The Strava sync endpoint returns `str(e)` in the error detail: `f"Strava sync failed: {str(e)}"`.

**Impact:** Internal exception messages (including stack traces, file paths, database errors) may be exposed to the client, aiding reconnaissance.

**Remediation:**
- Return a generic error message to the client: `"Strava sync failed. Please try again."`
- Log the full exception server-side
- Implement a global exception handler that sanitizes error responses

### 2.6 No Rate Limiting on Authentication Endpoints
**Severity:** High
**Files:** `app/routers/auth.py`, `app/routers/strava.py`

**Issue:** The `/api/auth/google` and `/api/strava/callback` endpoints have no rate limiting.

**Impact:** An attacker can brute-force Google ID tokens or flood the Strava OAuth callback endpoint, potentially causing account lockouts or denial of service.

**Remediation:**
- Add rate limiting middleware (e.g., `slowapi` or custom implementation)
- Limit `/api/auth/google` to 10 requests per minute per IP
- Limit `/api/strava/callback` to 5 requests per minute per IP

### 2.7 PDF Cache Stored in World-Readable `/tmp`
**Severity:** High
**Files:** `app/core/export/pdf_generator.py:32`

**Issue:** Generated PDFs are cached in `/tmp/pdf_cache`, which on many systems is world-readable. PDFs may contain user PII (name, email, training data, body weight).

**Impact:** Other processes or users on the same host could read cached PDF files containing personal training plans and health data.

**Remediation:**
- Use a user-private directory (e.g., `/app/private/pdf_cache` with `0700` permissions)
- Set restrictive file permissions on generated PDFs (`0600`)
- Add cache eviction on container restart

### 2.8 Database File and Backup in Repository Root
**Severity:** High
**Files:** Repository root: `app.db`, `runcoach.db`, `runcoach.db.backup`

**Issue:** SQLite database files exist in the project root. While `.gitignore` excludes `*.db` and `*.db.backup`, these files contain user data and could accidentally be committed or included in deployments.

**Impact:** Accidental exposure of production user data in version control or deployment artifacts.

**Remediation:**
- Delete `app.db`, `runcoach.db`, and `runcoach.db.backup` from the working directory
- Add a pre-commit hook to block database file commits
- Ensure `.dockerignore` excludes `*.db` and `*.db.backup` (currently missing)

---

## 3. MEDIUM — Input Validation & Injection

### 3.1 No Content-Type Security Headers
**Severity:** Medium
**Files:** `app/main.py`

**Issue:** The application does not set security headers:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy`

**Impact:** Increased risk of MIME-type sniffing attacks, clickjacking, and XSS exploitation.

**Remediation:**
- Add a middleware that sets security headers on all responses
- Consider using `starlette.middleware.security.SecurityMiddleware`

### 3.2 Cookie `Secure` Flag Tied to Debug Mode
**Severity:** Medium
**Files:** `app/middleware.py:31`, `app/routers/auth.py:68`

**Issue:** The `secure` flag on cookies is set to `not settings.debug`. If `DEBUG=False` but the app is served over HTTP (e.g., behind a misconfigured reverse proxy), cookies will still be sent over unencrypted connections.

**Impact:** Session cookies could be intercepted on unencrypted connections.

**Remediation:**
- Always set `secure=True` in production
- Add a `FORCE_SECURE_COOKIES` environment variable
- Ensure reverse proxy (Fly.io, Render) enforces HTTPS (Fly.io already has `force_https = true`)

### 3.3 Anonymous User ID Cookie Not Marked `Secure` in Production
**Severity:** Medium
**Files:** `app/middleware.py:24-32`

**Issue:** The `anonymous_user_id` cookie is set with `secure=not settings.debug`, same as the auth cookie. However, this cookie is used for plan ownership, and if intercepted, could allow session hijacking of anonymous plans.

**Impact:** An attacker on the same network could intercept the anonymous user ID and claim or modify plans.

**Remediation:**
- Set `secure=True` always in production (same fix as 3.2)
- Consider adding the `SameSite=Strict` attribute instead of `Lax`

### 3.4 Form Input Not Sanitized Before Template Rendering
**Severity:** Medium
**Files:** `app/routers/plans.py:61-188`, `app/routers/nutrition.py:24-80`

**Issue:** Form inputs (`current_km`, `target_distance`, `weeks`, etc.) are processed through Pydantic validation (good), but error messages constructed from user input are passed directly to templates. While Jinja2 auto-escapes by default, any custom template filters or raw HTML blocks could be vulnerable.

**Impact:** Potential stored XSS if error messages containing user input are persisted and later rendered without escaping.

**Remediation:**
- Audit all templates for `|safe` filter usage and `{% autoescape false %}` blocks
- Ensure all user-controlled data in error responses is sanitized
- Add Content-Security-Policy header to mitigate XSS impact

### 3.5 SQL Injection Risk via Raw String Concatenation (Low Risk)
**Severity:** Medium
**Files:** Multiple routers

**Issue:** While SQLAlchemy ORM is used throughout (which parameterizes queries), there are f-string log messages that include user-controlled data (e.g., plan IDs, user IDs). If any raw SQL queries exist, they could be vulnerable.

**Impact:** Currently mitigated by ORM usage, but future raw SQL additions could introduce injection.

**Remediation:**
- Enforce a code review policy requiring parameterized queries for all raw SQL
- Add a linter rule to flag `text()` or `exec_driver_sql()` usage
- Audit for any `session.execute(text(...))` calls with string formatting

### 3.6 No Request Size Limits
**Severity:** Medium
**Files:** `app/main.py`

**Issue:** FastAPI has no configured maximum request body size limit. An attacker could send extremely large payloads to consume memory.

**Impact:** Potential denial of service via memory exhaustion.

**Remediation:**
- Configure uvicorn with `--limit-concurrency` and `--backlog`
- Add middleware to reject requests exceeding a reasonable size (e.g., 1MB for JSON, 10MB for file uploads)
- Set `max_request_size` in reverse proxy configuration

### 3.7 Strava Client Credentials in Memory
**Severity:** Medium
**Files:** `app/config.py:63-64`, `app/services/strava_service.py:72`

**Issue:** `strava_client_id` and `strava_client_secret` are loaded into the `Settings` object at startup and remain in memory. If the process is dumped or inspected, credentials are exposed.

**Impact:** Compromise of Strava API credentials could allow an attacker to impersonate the application.

**Remediation:**
- Use a secrets manager (Fly.io secrets, AWS Secrets Manager)
- Minimize the lifetime of secrets in memory where possible
- Add memory protection (e.g., `mlock`) if running on dedicated hardware

---

## 4. LOW — Operational & Infrastructure

### 4.1 SQLite Not Suitable for Production Multi-User Workloads
**Severity:** Low
**Files:** `fly.toml:13`, `render.yaml:22`

**Issue:** SQLite is used as the production database. While Fly.io mounts a persistent volume, SQLite has limitations with concurrent writes and is not designed for multi-tenant production workloads.

**Impact:** Under load, SQLite may experience write contention, database locking, or corruption. The `busy_timeout=5000` mitigates but doesn't eliminate this.

**Remediation:**
- Migrate to PostgreSQL (Render.yaml already has commented-out PostgreSQL config)
- Use Fly.io's managed Postgres add-on
- Run Alembic migration to transfer data

### 4.2 Database Seed File Baked into Docker Image
**Severity:** Low
**Files:** `Dockerfile:27`, `start.sh:9-10`

**Issue:** The `runcoach.db` is copied into the Docker image as `runcoach.db.seed`. This means any user data present at build time is baked into every deployment image.

**Impact:** If the image is pulled or inspected, user data from the build-time database snapshot is exposed.

**Remediation:**
- Seed the database with an empty schema only (no user data)
- Use Alembic migrations to create the schema on first boot
- Remove `COPY runcoach.db ./runcoach.db.seed` from Dockerfile

### 4.3 No Health Check Authentication
**Severity:** Low
**Files:** `app/main.py:146-148`, `fly.toml:26-31`

**Issue:** The `/health` endpoint is publicly accessible and returns the application version. While not critical, it provides version enumeration.

**Impact:** An attacker can determine the exact application version to target known vulnerabilities.

**Remediation:**
- Restrict health check to internal network only (Fly.io internal port)

### 4.4 Container Runs as Non-Root User (Good, but Incomplete)
**Severity:** Low
**Files:** `Dockerfile:33-37`

**Issue:** The Dockerfile creates an `appuser` and switches to it (good). However, the `/tmp/pdf_cache` directory is created at runtime by the `PDFGenerator` class and may have default permissions.

**Impact:** PDF cache files may be readable by other processes on the same host.

**Remediation:**
- Create the cache directory in the Dockerfile with `0700` permissions owned by `appuser`
- Or use an in-memory cache (e.g., `cachetools.TTLCache`) instead of filesystem

### 4.5 Dependencies Contain Known Vulnerabilities
**Severity:** Low
**Files:** `requirements.txt`

**Issue:** Several dependencies are outdated and may have known CVEs:
- `fastapi==0.104.1` (released Oct 2023 — current is 0.115+)
- `httpx==0.25.2` (released Nov 2023 — current is 0.28+)
- `requests==2.31.0` (has known CVEs in urllib3 dependency)
- `python-jose[cryptography]==3.3.0` (last release 2020, unmaintained)

**Impact:** Known vulnerabilities in dependencies could be exploited.

**Remediation:**
- Run `pip-audit` or `safety check` to identify CVEs
- Update all dependencies to latest stable versions
- Replace `python-jose` with `PyJWT` (actively maintained)
- Add dependency scanning to CI/CD pipeline

---

## 5. PRIVACY CONCERNS

### 5.1 Health Data Collected Without Explicit Consent
**Severity:** Medium
**Files:** Multiple

**Issue:** The application collects sensitive health data (heart rate, weight, sleep quality, soreness, energy levels, stress) without a privacy policy or explicit consent mechanism.

**Impact:** Regulatory compliance risk (GDPR, CCPA, HIPAA-adjacent). Users may not be aware their health data is being stored.

**Remediation:**
- Add a privacy policy page
- Implement explicit consent for health data collection
- Add data export and deletion endpoints (right to be forgotten)

### 5.2 No Data Retention Policy
**Severity:** Medium
**Files:** N/A (operational)

**Issue:** User data (runs, plans, readiness logs, Strava tokens) is retained indefinitely with no automated cleanup.

**Impact:** Increased liability if the database is compromised; regulatory non-compliance.

**Remediation:**
- Implement automated data retention policies (e.g., delete inactive accounts after 2 years)
- Add a "Delete My Account" endpoint that cascades to all related data
- Document retention policy in privacy policy

### 5.3 Strava Token Refresh Stored Indefinitely
**Severity:** Medium
**Files:** `app/models/user.py:23-26`

**Issue:** Strava access tokens, refresh tokens, and athlete IDs are stored in the database. Even with `EncryptedString`, the refresh token allows indefinite access to the user's Strava data.

**Impact:** If the encryption key is compromised, an attacker gains access to all users' Strava accounts.

**Remediation:**
- Implement token revocation on user logout or account deletion
- Add a "Disconnect Strava" endpoint that clears all Strava fields
- Consider encrypting refresh tokens with a separate key

### 5.4 Anonymous User Tracking Without Disclosure
**Severity:** Low
**Files:** `app/middleware.py:10-34`

**Issue:** The application sets an `anonymous_user_id` cookie on every visitor without disclosure or consent.

**Impact:** Privacy regulation compliance risk (GDPR requires consent for tracking cookies).

**Remediation:**
- Add a cookie consent banner
- Classify `anonymous_user_id` as a strictly necessary cookie (document in privacy policy)
- Or delay cookie creation until user interacts with plan generation

---

## 6. INFRASTRUCTURE HARDENING

### 6.1 Fly.io Configuration
**Current:** `fly.toml` with `force_https = true` (good), 512MB RAM, 1 CPU

**Recommendations:**
- Add `auto_rollback = true` for safer deployments
- Set `min_machines_running = 1` to prevent cold-start data loss
- Add `[[services.ports]]` with `handlers = ["http"]` and `force_https = true` for explicit HTTP→HTTPS redirect
- Use Fly.io secrets for `SECRET_KEY` and `GOOGLE_CLIENT_ID` (documented but verify)
- Enable Fly.io's built-in DDoS protection
- Add monitoring and alerting (Fly.io metrics, Sentry integration)

### 6.2 Docker Image Hardening
**Current:** `python:3.11.12-slim` base image

**Recommendations:**
- Pin to a specific digest: `python:3.11.12-slim@sha256:...`
- Add `RUN apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*` for minimal attack surface
- Run `pip install --no-cache-dir` (already done)
- Add `.dockerignore` entries for `*.db`, `*.db.backup`, `.env`, `pdf_cache/`
- Scan image with `trivy` or `grype` before deployment
- Add `--cap-drop=ALL --cap-add=NET_BIND_SERVICE` if running with Docker directly

### 6.3 TLS/SSL Configuration
**Current:** Relies on platform (Fly.io/Render) for TLS termination

**Recommendations:**
- Verify TLS 1.2+ enforcement at the platform level
- Add HSTS header: `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- Ensure certificate auto-renewal is enabled
- Test with SSL Labs or equivalent

---

## 7. IMPLEMENTATION PRIORITY

### Phase 1 — Critical (Week 1)
1. Remove debug endpoints or gate behind separate env var (1.1)
2. Remove JWT from API response body (1.2)
3. Add CSRF protection (1.3)
4. Fix EncryptedString plaintext fallback (1.5)
5. Separate encryption key from JWT signing key (1.6)
6. Add rate limiting to auth endpoints (2.6)

### Phase 2 — High (Week 2)
7. Fix shared plan PII leakage (2.1)
8. Remove `user_id` from API responses (2.3)
9. Sanitize error messages (2.5)
10. Fix Strava callback validation (1.4)
11. Remove email from auth logs (2.4)
12. Secure PDF cache directory (2.7)
13. Clean up database files from repo (2.8)

### Phase 3 — Medium (Week 3) ✅ DONE
14. ✅ Add security headers middleware (3.1)
15. ✅ Fix cookie secure flag handling (3.2, 3.3)
16. ✅ Audit templates for XSS (3.4) — no `|safe` or `autoescape false` found; CSP via headers
17. ✅ Add request size limits (3.6)
18. ✅ Add privacy policy and consent (5.1, 5.4)
19. ✅ Implement data retention and account deletion (5.2, 5.3)

### Phase 4 — Infrastructure (Week 4) ✅ DONE (except PostgreSQL)
20. ✅ Update dependencies and replace python-jose with PyJWT (4.5)
21. ✅ Harden Docker image and .dockerignore (6.3, 4.4)
22. ⏭️ Migrate to PostgreSQL (4.1) — deferred, SQLite sufficient for now
23. ✅ Remove DB seed from image (4.2) — Alembic creates schema on first boot
24. ✅ Add deployment safety: rolling strategy in fly.toml (6.1)
25. ✅ Configure TLS/HSTS (6.4) — already in Phase 3 security_headers middleware

### Phase 5 — Privacy Hardening ✅ DONE
26. ✅ Cookie consent banner (5.4) — banner in base.html, stored in localStorage
27. ✅ Health data consent via cookie notice (5.1) — consent banner covers health data collection
28. ✅ Delay anonymous_user_id cookie until user interaction (5.4) — only set on /generate-plan or /api/ paths
29. ✅ Automated inactive account cleanup on startup (5.2) — cleanup_service.py, runs on deploy
30. ✅ Strava token revocation via API on disconnect (5.3) — calls /oauth/deauthorize
31. ✅ Strava token revocation on account deletion (5.3) — revokes before cascading delete

### Phase 6 — Infrastructure Hardening II ✅ DONE
32. ✅ Pin Docker base image by digest (6.2) — sha256 digest prevents tag mutation
33. ✅ Add liveness check to fly.toml (6.1) — separate from http_service health check
34. ✅ Add release_command for pre-deploy migration validation (6.1)
35. ✅ Update privacy policy with cookie consent details (5.1, 5.4)

---

## 8. TESTING & VALIDATION

After implementing fixes, validate with:

1. **Automated Scanning:**
   - `pip-audit` for dependency CVEs
   - `bandit -r app/` for Python security issues
   - `trivy image <image>` for container vulnerabilities
   - OWASP ZAP or Burp Suite for DAST

2. **Manual Testing:**
   - CSRF bypass attempts on all state-changing endpoints
   - JWT token manipulation (alg:none, expired, tampered)
   - IDOR testing on all `/api/runs/*`, `/api/plan/*`, `/api/recipes/*` endpoints
   - XSS testing on form inputs and error messages
   - Cookie interception tests (if HTTP is accessible)

3. **Penetration Testing:**
   - Engage a third-party pentest before major release
   - Focus on authentication flow, Strava integration, and plan sharing

---

## 9. ONGOING MAINTENANCE

- Run `pip-audit` weekly in CI/CD
- Review and rotate `SECRET_KEY` and `ENCRYPTION_KEY` quarterly
- Audit access logs monthly for anomalous patterns
- Keep a security contact email for vulnerability reports
- Document security incident response procedure
