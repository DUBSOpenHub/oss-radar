# 🔒 Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| latest  | ✅ Yes             |

## Reporting a Vulnerability

We take the security of OSS Radar seriously. If you discover a security
vulnerability, please report it responsibly.

### How to Report

1. **Preferred**: Use [GitHub Security Advisories](https://github.com/DUBSOpenHub/oss-radar/security/advisories/new)
   to report vulnerabilities privately.
2. **Alternative**: Email **security@dubsopenhub.com** with details of the
   vulnerability.

**Please do NOT open a public issue for security vulnerabilities.**

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### In Scope

- Credential exposure in scraper configurations
- SMTP credential handling
- Reddit API credential handling
- Injection via crafted forum data
- Email content injection

### Out of Scope

- Vulnerabilities in upstream forum platforms
- Vulnerabilities in third-party APIs (Reddit, etc.)
- Issues requiring physical access to the machine

### Response Timeline

| Action          | Timeframe |
| --------------- | --------- |
| Acknowledgment  | 24 hours  |
| Assessment      | 72 hours  |
| Fix (if needed) | Best effort, depends on severity |
