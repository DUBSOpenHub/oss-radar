# Security Review: Email, CLI, Config, and Scheduling Modules

**Review Date:** 2026-03-04  
**Task ID:** task-008  
**Scope:** radar/email/sender.py, radar/cli.py, radar/config.py, radar/scheduling/scheduler.py  

## Executive Summary

Found **8 security issues** across 4 files: SMTP credential handling vulnerabilities, improper state mutation, cron validation gaps, and insufficient input validation. Most are medium risk; one is high risk (credential leakage).

---

## Detailed Findings

### 1. ⚠️ HIGH: SMTP Credential Leakage via email_from Fallback
**File:** `radar/email/sender.py`, line 116  
**Severity:** HIGH  
**Category:** Information Disclosure

```python
msg["From"] = self.config.email_from or self.config.smtp_user
```

**Issue:** If `email_from` is not explicitly configured, the SMTP username is used as the "From" address. In typical deployments, SMTP username = email account (e.g., `alerts@company.com`), so this isn't directly leaking credentials. However, if someone misconfigures and uses a service account username format (e.g., `service+api_key@example.com`), the key exposure risk increases.

**Recommendation:** Require explicit `email_from` configuration when `email_enabled=true`. Validate in Settings model:
```python
@model_validator(mode="after")
def validate_email_from_when_enabled(self) -> "Settings":
    if self.email_enabled and not self.email_from:
        raise ValueError("RADAR_EMAIL_FROM required when EMAIL_ENABLED=true")
    return self
```

**Impact:** Medium - depends on deployment practices.

---

### 2. ⚠️ MEDIUM: Insufficient SMTP Credential Validation Before Login Attempt
**File:** `radar/email/sender.py`, line 89  
**Severity:** MEDIUM  
**Category:** Improper Error Handling

```python
if self.config.smtp_host and self.config.smtp_user:
    for attempt in range(1, 3):
        try:
            self._send_smtp(msg, recipients)
```

**Issue:** Only checks `smtp_host` and `smtp_user` exist, but not `smtp_password`. If password is empty string (common with unset GitHub Secrets), the code attempts login without password, which fails silently and falls back to sendmail. No explicit error message differentiates "bad password" from "network unreachable."

**Recommendation:** Validate password before attempting SMTP:
```python
if self.config.smtp_host and self.config.smtp_user and self.config.smtp_password:
```

**Impact:** Medium - degrades gracefully but logs are ambiguous.

---

### 3. ⚠️ MEDIUM: Plain-Text Credential Storage in Settings Object
**File:** `radar/config.py`, lines 37-38  
**Severity:** MEDIUM  
**Category:** Sensitive Data Exposure

```python
smtp_password: str = ""
redis_client_secret: str = ""
```

**Issue:** Credentials are stored as plain-text string fields in a Pydantic model. The `__repr__` masks them during logging, but the values remain accessible at runtime via reflection or memory inspection. No encryption at rest or in transit (relies on `BaseSettings` env var loading only).

**Recommendation:** 
- Implement a `SecretStr` wrapper from `pydantic` (already available):
```python
from pydantic import SecretStr
smtp_password: SecretStr = SecretStr("")
```
- Access via `.get_secret_value()` when needed.
- Update Settings model in `radar/config.py` to use `SecretStr` for all credential fields.

**Impact:** Medium - requires privileged access to process memory to exploit.

---

### 4. ⚠️ MEDIUM: Missing SMTP Password Configuration Validation
**File:** `radar/config.py`  
**Severity:** MEDIUM  
**Category:** Improper Input Validation

**Issue:** No validator ensures that if `email_enabled=true` AND `smtp_user` is set, then `smtp_password` must also be set. Currently allows email enabled with partial SMTP config.

**Recommendation:** Add model validator:
```python
@model_validator(mode="after")
def validate_smtp_complete_when_required(self) -> "Settings":
    """SMTP password must be set if SMTP user is configured and email enabled."""
    if self.email_enabled and self.smtp_user and not self.smtp_password:
        raise ValueError(
            "RADAR_SMTP_PASSWORD required when RADAR_EMAIL_ENABLED=true "
            "and RADAR_SMTP_USER is set"
        )
    return self
```

**Impact:** Medium - prevents partial SMTP misconfiguration.

---

### 5. ⚠️ MEDIUM: Improper State Mutation via object.__setattr__
**File:** `radar/cli.py`, lines 96, 167  
**Severity:** MEDIUM  
**Category:** Improper Configuration Management

```python
object.__setattr__(cfg, "email_enabled", False)
```

Used in `daily` and `weekly` commands to bypass Pydantic immutability (if frozen=True). This is fragile:
- Bypasses model validators
- Works around intentional configuration constraints
- Relies on implementation detail of Pydantic

**Recommendation:** Create a new Settings copy instead:
```python
if no_email:
    cfg_dict = cfg.model_dump()
    cfg_dict["email_enabled"] = False
    cfg = Settings(**cfg_dict)
```

Or use a context manager approach to override email behavior at dispatch time, not config time.

**Impact:** Medium - bypasses validation logic.

---

### 6. ⚠️ MEDIUM: No Cron String Validation Before Job Registration
**File:** `radar/scheduling/scheduler.py`, lines 47-49, 69-71, 91-93  
**Severity:** MEDIUM  
**Category:** Improper Input Validation

```python
def _register_scrape(self) -> None:
    cron_parts = self.config.scrape_cron.split()
    if len(cron_parts) != 5:
        raise ValueError(f"Invalid scrape_cron: {self.config.scrape_cron!r}")
    
    minute, hour, day, month, day_of_week = cron_parts
    self._scheduler.add_job(..., trigger=CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week
    ))
```

**Issue:** Only validates that exactly 5 parts exist, but does NOT validate each part is a valid cron expression (e.g., `minute` must be 0-59, `*`, `*/n`, or list like `1,3,5`). Invalid values like `minute="99"` or `hour="invalid"` will silently fail when APScheduler tries to create the CronTrigger.

**Recommendation:** Use APScheduler's built-in validation or validate each field:
```python
from apscheduler.triggers.cron import CronTrigger
try:
    trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)
except ValueError as e:
    raise ValueError(f"Invalid cron expression {self.config.scrape_cron!r}: {e}")
```

**Impact:** Medium - malformed cron expressions prevent scheduler from starting.

---

### 7. ⚠️ LOW: Hardcoded Test Query in Validation Command
**File:** `radar/cli.py`, line 209  
**Severity:** LOW  
**Category:** Information Disclosure (Minor)

```python
r = httpx.get("https://hn.algolia.com/api/v1/search?query=test&hitsPerPage=1", timeout=10)
```

**Issue:** The hardcoded query string `query=test` is sent to an external API during validation. While benign, it creates a minor information leak (network log shows validation occurred) and is unnecessary for connectivity testing.

**Recommendation:** Use a minimal query or HEAD request:
```python
r = httpx.head("https://hn.algolia.com/api/v1/", timeout=10)
```

**Impact:** Low - negligible security impact.

---

### 8. ⚠️ LOW: No Timeout on SMTP Connections
**File:** `radar/email/sender.py`, line 126  
**Severity:** LOW  
**Category:** Denial of Service

```python
with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
```

**Issue:** SMTP connection created without explicit timeout. If SMTP server is slow/unresponsive, the connection attempt blocks indefinitely.

**Recommendation:** Add timeout parameter:
```python
with smtplib.SMTP(
    self.config.smtp_host, 
    self.config.smtp_port, 
    timeout=self.config.request_timeout or 10
) as server:
```

**Impact:** Low - sendmail fallback mitigates most cases.

---

## Summary of Recommendations

| Finding | Severity | Quick Fix | File |
|---------|----------|-----------|------|
| email_from fallback to smtp_user | HIGH | Add validator requiring email_from | config.py |
| Incomplete SMTP credential check | MEDIUM | Check smtp_password exists | sender.py |
| Plain-text credential storage | MEDIUM | Use SecretStr for passwords | config.py |
| Missing SMTP password validator | MEDIUM | Add model validator | config.py |
| Monkey-patching email_enabled | MEDIUM | Use Settings copy instead | cli.py |
| No cron validation | MEDIUM | Validate with CronTrigger | scheduler.py |
| Hardcoded test query | LOW | Use HEAD request instead | cli.py |
| No SMTP timeout | LOW | Add timeout parameter | sender.py |

---

## Next Steps

1. **Immediate:** Add email_from and smtp_password validators to Settings (high-impact, low-effort)
2. **Short-term:** Replace monkey-patching, fix cron validation, add SMTP timeout
3. **Medium-term:** Integrate SecretStr for all credential fields
4. **Testing:** Add integration tests for SMTP credential failure modes

