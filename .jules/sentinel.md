## 2024-05-24 - Timing Attack Vulnerability in Password Verification
**Vulnerability:** The `_verify_password` function in `apps/chat/demo_server_v6.py` compares hashes using standard string equality (`==`). This is vulnerable to timing attacks, where an attacker can determine the expected hash character by character by measuring the time it takes for the comparison to fail.
**Learning:** Even when using standard cryptographic hashes, string comparison is not constant-time.
**Prevention:** Always use constant-time comparison functions like `hmac.compare_digest` for verifying passwords, tokens, or any security-sensitive strings.

## 2024-05-24 - Plain-text Fallback in Password Verification
**Vulnerability:** The `_verify_password` function falls back to a plain-text comparison (`stored_hash == supplied`) if the `stored_hash` does not start with the `sha256:` prefix. This contradicts the memory learning: "Secure password storage in the repository uses SHA-256 hashing with a `sha256:` prefix; plain-text fallback for authentication is explicitly prohibited."
**Learning:** Legacy configurations can easily re-introduce security vulnerabilities if fallback mechanisms are not strictly controlled or deprecated.
**Prevention:** Remove plain-text fallback completely and enforce strict hash prefixes.
