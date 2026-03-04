# Code Review: radar/scraping/base.py & radar/scraping/http.py

## Executive Summary

**Grade: B+** — Production-ready with critical security hardening needed.

Both modules demonstrate strong error handling and above-average SSRF protection. However, a **redirect-based SSRF bypass** exists that should be addressed before production use. All current tests pass (11/11). Detailed findings below.

---

## STRENGTHS

### 1. Robust SSRF Protection (http.py, Lines 100–119)

The `_assert_safe()` method implements DNS-based SSRF validation:

- **Pre-request DNS resolution** prevents most SSRF vectors
- **Blocks private IP ranges**: RFC-1918 (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16), loopback (127.0.0.0/8), IPv6 private (fc00::/7, ::1/128)
- **Multi-homed host awareness**: Checks ALL resolved IPs, not just the first
- **Safe-by-default**: DNS failures block the request (fail secure)

**Code quality**: Clear variable names, proper exception handling, readable logic.

### 2. Proper Retry Strategy (http.py, Lines 121–145)

Tenacity-based exponential backoff with intelligent error discrimination:

- **Retries only transient errors**: `TimeoutException`, `NetworkError`, `ConnectError`
- **Fails fast on HTTP errors**: 4xx/5xx responses raise immediately (line 131: `raise_for_status()`)
- **Exponential backoff**: 2–30s prevents retry storms
- **Max 3 attempts** reasonable for scraping workloads
- **reraise=True** ensures exceptions propagate after exhaustion

**Impact**: Balances resilience with resource efficiency.

### 3. Error Isolation & Pipeline Resiliency (base.py, Lines 44–57)

The `scrape()` wrapper method:

- Catches **all exceptions** from `fetch_raw()`
- Returns **empty list** instead of raising (prevents pipeline halt)
- Logs errors with **contextual metadata** (platform, error message, stack trace)
- Allows failed scrapers to fail gracefully without affecting others

**Pipeline behavior**: One failing scraper (e.g., rate-limited API) doesn't prevent other scrapers from running.

### 4. Dedup Key Logic (base.py, Lines 71–74)

URL deduplication is sound:

- SHA-256 produces stable, collision-free keys
- Normalization handles common variations:
  - Trailing slash (https://example.com/post/ == https://example.com/post)
  - Case sensitivity (https://example.com == https://EXAMPLE.COM)
  - Whitespace (strips leading/trailing)
- 64-character hex digest is database-friendly

### 5. Defensive Post Construction (base.py, Lines 76–93)

Graceful handling of incomplete/malformed API responses:

- Uses `.get()` with defaults instead of direct indexing
- Type coercion (`str()`, `int()`) prevents downstream crashes
- Missing fields → sensible zero/empty defaults
- Prevents silent data loss

---

## CRITICAL ISSUES

### [HIGH] 1. Redirect-Based SSRF Bypass

**Location**: Lines 68, 130, 143

**Problem**: `httpx.Client` is configured with `follow_redirects=True` by default. An attacker-controlled external URL can redirect to localhost, **bypassing the initial SSRF check**.

**Attack Scenario**:
```
1. Attacker provides URL: https://attacker.com/redirect
2. Initial _assert_safe() resolves attacker.com → 93.184.216.34 (safe ✓)
3. httpx.get() follows redirect: 303 to http://127.0.0.1:8080/admin
4. Client makes request to localhost without re-validation
5. SSRF successful: attacker reached internal service
```

**Real-world impact**: Moderate. Requires attacker to control redirect destination AND have knowledge of internal services.

**Recommendation**:
```python
# Option A (RECOMMENDED): Disable redirects entirely
self._client = httpx.Client(
    timeout=httpx.Timeout(timeout),
    follow_redirects=False,  # Disable redirects
    headers={"User-Agent": "oss-radar/1.0"},
)
# Rationale: Scrapers typically care about the final content-type and status.
#           If a feed/article URL redirects, the scraper can handle 3xx.

# Option B: Validate final URL after redirects (complex)
# Requires custom transport hook to inspect redirect chain.
# Not recommended for simplicity.

# Option C: Limit redirect chain depth (defensive)
# follow_redirects=True with max 1 redirect
# Still vulnerable to single-hop redirects.
```

**Fix complexity**: Minimal (1 line change to `follow_redirects=False`).

**Affected code**:
- Line 68: Initial client config
- Lines 130, 143: GET/POST methods rely on redirects

---

### [MEDIUM] 2. Missing Exception Handling in __init__

**Location**: Lines 66–70

**Problem**: If `httpx.Client()` initialization fails, `self._client` remains uninitialized. Subsequent calls to `close()` or `__exit__()` crash.

**Example failure**:
```python
# Thread-local httpx state corrupted, httpx.Client() raises RuntimeError
client = SafeHTTPClient()  # RuntimeError: event loop in wrong thread
try:
    client.get(...)  # Fails silently (AttributeError on self._client)
finally:
    client.close()  # AttributeError: 'SafeHTTPClient' has no attribute '_client'
```

**Recommendation**:
```python
def __init__(self, timeout: int = 10, ...) -> None:
    self.timeout = timeout
    self.max_retries = max_retries
    self.min_wait = min_wait
    self.max_wait = max_wait
    try:
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            headers={"User-Agent": "oss-radar/1.0"},
        )
    except Exception as e:
        logger.error(f"Failed to initialize HTTP client: {e}")
        raise

def close(self) -> None:
    if hasattr(self, '_client') and self._client:
        self._client.close()
```

**Fix complexity**: Minimal (try/except + hasattr guard).

---

## MEDIUM PRIORITY ISSUES

### 3. Incomplete Private IP Ranges

**Location**: Lines 19–26

**Current coverage**:
```python
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),    # Loopback ✓
    ipaddress.ip_network("10.0.0.0/8"),     # RFC-1918 ✓
    ipaddress.ip_network("172.16.0.0/12"),  # RFC-1918 ✓
    ipaddress.ip_network("192.168.0.0/16"), # RFC-1918 ✓
    ipaddress.ip_network("::1/128"),        # IPv6 loopback ✓
    ipaddress.ip_network("fc00::/7"),       # IPv6 unique local ✓
]
```

**Missing ranges**:
| Range | Type | Risk | Notes |
|-------|------|------|-------|
| `0.0.0.0/8` | This network | Low | Source validation; unlikely in URLs |
| `169.254.0.0/16` | Link-local | Medium | DHCP fallback; can reach local services |
| `fe80::/10` | IPv6 link-local | Medium | IPv6 equivalent of 169.254.0.0/16 |
| `224.0.0.0/4` | IPv4 multicast | Low | Broadcast; unlikely exploitable |
| `240.0.0.0/4` | IPv4 reserved | Low | Unassigned; unlikely in practice |
| `ff00::/8` | IPv6 multicast | Low | Broadcast analog |

**Recommendation**: Add at minimum:
```python
_PRIVATE_NETWORKS = [
    # ... existing ranges ...
    ipaddress.ip_network("169.254.0.0/16"),  # DHCP link-local
    ipaddress.ip_network("fe80::/10"),       # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),       # This network
]
```

**Impact**: Medium — Unlikely to be exploited, but defense-in-depth good practice.

---

### 4. No Tests for SSRF Protection

**Location**: tests/test_scraping.py

**Current coverage**: 11 tests, all functional
- ✓ Error isolation in `scrape()`
- ✓ Dedup key normalization
- ✓ Post construction with defaults
- ✗ SSRF blocking (no tests)
- ✗ Redirect behavior (no tests)
- ✗ Retry exhaustion (no tests)

**Recommended tests**:
```python
def test_blocks_localhost_ipv4():
    client = SafeHTTPClient()
    with pytest.raises(SSRFError):
        client._assert_safe("http://127.0.0.1:8080")

def test_blocks_private_ip_10_network():
    client = SafeHTTPClient()
    with pytest.raises(SSRFError):
        client._assert_safe("http://10.0.0.5")

def test_blocks_dns_failure():
    """DNS resolution failure should block request (safe-by-default)."""
    client = SafeHTTPClient()
    with pytest.raises(SSRFError) as exc:
        client._assert_safe("http://nonexistent.invalid.test.local")
    assert "DNS resolution failed" in str(exc.value)

def test_allows_public_url():
    """Public URLs should pass SSRF check."""
    client = SafeHTTPClient()
    client._assert_safe("https://news.ycombinator.com")  # Should not raise
```

**Impact**: Low — Security assumptions should be validated explicitly.

---

## LOW PRIORITY OBSERVATIONS

### 5. Type Annotation Consistency

**Location**: base.py, line 26

Minor inconsistency:
```python
def __init__(self, config: Settings, client: SafeHTTPClient | None = None) -> None:
    # ✓ Has return type hint
```

Expected everywhere. Not a bug, just style.

---

### 6. Timeout Behavior with Retries

**Location**: Lines 121–145

**Observation**: Each retry attempt uses the full `timeout` duration. With `max_retries=3` and `timeout=10s`, total request time could exceed 30+ seconds:

```
Attempt 1: 10s timeout
Wait: 2s exponential backoff
Attempt 2: 10s timeout
Wait: 4s exponential backoff
Attempt 3: 10s timeout
Total: ~36 seconds (not 10 seconds)
```

**Impact**: Low for scraping context (usually acceptable), but worth documenting in docstring.

**Recommendation**: Add docstring note:
```python
def get(self, url: str, **kwargs: Any) -> httpx.Response:
    """SSRF-protected GET with tenacity retries.
    
    Note: Total request time may exceed timeout due to retry exponential backoff.
    With max_retries=3 and timeout=10s, worst case ~36s.
    """
```

---

## SECURITY ASSESSMENT MATRIX

| Category | Status | Notes |
|----------|--------|-------|
| **SSRF Protection** | ⚠️ Good + Vulnerable | DNS-based checks strong. Redirect bypass (HIGH). |
| **Error Handling** | ✅ Excellent | Graceful degradation, full exception isolation. |
| **Retry Logic** | ✅ Good | Exponential backoff, intelligent error filtering. |
| **Input Validation** | ✅ Good | URL parsing, type coercion, defensive defaults. |
| **Resource Cleanup** | ⚠️ Incomplete | Missing try/finally in `__init__`. |
| **Test Coverage** | ⚠️ Partial | Functional tests complete; security tests missing. |

---

## CORRECTNESS ASSESSMENT

### radar/scraping/base.py
**Verdict**: ✅ **Correct**

- Error isolation logic is sound
- Dedup key derivation is valid
- Type coercion is defensive and appropriate
- No logical errors detected

### radar/scraping/http.py
**Verdict**: ⚠️ **Mostly Correct (with security risk)**

- SSRF validation logic is thorough and correct
- Retry strategy is well-designed
- **Risk**: `follow_redirects=True` enables redirect-based SSRF bypass (known attack vector)
- Missing initialization exception handling

---

## RECOMMENDATIONS (Priority Order)

### Critical
1. **Disable `follow_redirects`** in http.py line 68
   - 1-line fix
   - Eliminates redirect SSRF bypass
   - Verify scrapers handle 3xx gracefully

### High
2. **Add exception handling** in http.py `__init__`
   - Try/except around httpx.Client initialization
   - Add hasattr check in close()
   - Prevents AttributeError crashes

3. **Expand IP range coverage** in http.py
   - Add `169.254.0.0/16`, `fe80::/10`, `0.0.0.0/8`
   - Defense-in-depth for IPv6 link-local scenarios

### Medium
4. **Add SSRF/redirect tests** to test_scraping.py
   - `test_blocks_localhost_ipv4`
   - `test_blocks_dns_failure`
   - `test_allows_public_url`
   - Validates security assumptions

### Low
5. **Type annotation consistency**
   - Minor style issue, not functional

---

## VALIDATION RESULTS

**Existing Tests**: 11/11 PASS ✅
- `test_fetch_returns_raw_posts` — data parsing works
- `test_scrape_isolates_errors` — error handling works
- `test_dedup_across_tags` — dedup logic works
- `test_dedup_key_is_sha256` — hash generation correct
- All error isolation and type coercion tests pass

**Code Review Findings**:
- 1 critical vulnerability (redirect SSRF)
- 2 medium issues (exception handling, IP ranges)
- 2 low issues (type hints, test coverage)

---

## CONCLUSION

**Production Readiness: B+ → A- with fixes**

The codebase is **well-structured and thoughtfully designed**. SSRF protection is above average. However, the **redirect bypass is a known attack vector** that must be fixed before production. Once the critical and high-priority fixes are applied, this code is solid and maintainable.

**Estimated effort to address all issues**: ~2 hours
- 15 min: Disable follow_redirects + test scrapers still work
- 30 min: Exception handling + IP range expansion
- 45 min: Add comprehensive SSRF tests
- 30 min: Code review, edge case testing

**Overall assessment**: Ship with recommended fixes. The foundation is strong.

---

## APPENDIX: Attack Scenarios

### Scenario 1: Redirect to Localhost (Current Vulnerability)
```
Scraper URL: https://attacker.com/article
1. _assert_safe("https://attacker.com/article")
   → DNS: attacker.com = 93.184.216.34 (public IP, safe ✓)
2. httpx.get("https://attacker.com/article")
   → HTTP 301 to http://127.0.0.1:8080/admin
3. httpx follows redirect (follow_redirects=True)
   → Makes request to 127.0.0.1:8080 WITHOUT re-validation
4. SSRF successful: attacker accessed internal admin panel

Fix: Set follow_redirects=False
After fix: httpx returns 301, scraper handles it or fails (expected behavior)
```

### Scenario 2: DNS Failure (Defended Against ✓)
```
Scraper URL: http://very-long-unicode-url-that-causes-dns-to-timeout.test
1. _assert_safe(...) calls socket.getaddrinfo()
   → socket.gaierror (DNS timeout/NX)
2. _assert_safe raises SSRFError("DNS resolution failed...")
3. Request blocked

Status: ✓ Protected
```

### Scenario 3: Private IP Direct (Defended Against ✓)
```
Scraper URL: http://192.168.1.1
1. _assert_safe(...) resolves 192.168.1.1
2. Checks if 192.168.1.1 in _PRIVATE_NETWORKS[...]
3. Matches RFC-1918 range → SSRFError
4. Request blocked

Status: ✓ Protected
```

---

## References

- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [CWE-918: Server-Side Request Forgery (SSRF)](https://cwe.mitre.org/data/definitions/918.html)
- [RFC-1918: Address Allocation for Private Internets](https://tools.ietf.org/html/rfc1918)
- [httpx Documentation: Redirects](https://www.python-httpx.org/api/#client)
