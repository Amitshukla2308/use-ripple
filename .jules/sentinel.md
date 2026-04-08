## 2025-01-20 - Plaintext Password Fallback and Timing Attack Fix
**Vulnerability:** Plain-text password fallback and non-constant time string comparison.
**Learning:** Legacy configuration support introduced a plain-text fallback bypassing the hashing mechanism, and standard string comparison allows timing attacks.
**Prevention:** Remove plain-text fallbacks and use `hmac.compare_digest` for secure, constant-time comparison of hashes.