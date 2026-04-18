## 2026-04-10 - Legacy plain-text passwords
**Vulnerability:** The password verification function `_verify_password` allowed legacy plain-text fallback, matching user-supplied passwords directly against the database hash/value if it didn't start with `sha256:`.
**Learning:** Legacy configurations can lead to serious security gaps like storing and comparing plain text passwords. They must be removed.
**Prevention:** Hard fail if the stored password string does not match the expected secure hashing schema.

## 2025-02-14 - Fix Command Injection Vulnerabilities in Subprocess Execution
**Vulnerability:** Unsanitized user inputs and dynamic strings were being passed to `subprocess.run(..., shell=True)` across various files (`apps/cli/commands/code_commands.py`, `apps/cli/commands/system_commands.py`, `apps/cli/commands/git_commands.py`), leading to potential arbitrary command execution vulnerabilities.
**Learning:** The usage of `shell=True` allows chaining commands using operators like `;`, `&&`, or `|`. When mixed with string formatting, it creates high risks of OS command injection. Many operations don't need a shell (e.g. running linters or fuser). Operations searching for executables should leverage the standard library (`shutil.which()`) instead of launching a shell just to run `which`.
**Prevention:** Avoid `shell=True` where possible. Pass commands as a list of arguments (`shell=False`). Use `shlex.split()` to safely parse dynamic argument strings. Use `shutil.which()` to find executables.
