## 2026-04-10 - Legacy plain-text passwords
**Vulnerability:** The password verification function `_verify_password` allowed legacy plain-text fallback, matching user-supplied passwords directly against the database hash/value if it didn't start with `sha256:`.
**Learning:** Legacy configurations can lead to serious security gaps like storing and comparing plain text passwords. They must be removed.
**Prevention:** Hard fail if the stored password string does not match the expected secure hashing schema.
