"""
git_commands.py — Git-related slash commands.

Ported from codetoolcli: commit, commit-push, push, diff, review-pr, pr.
Uses the engine for LLM-assisted commit messages and PR reviews.
"""
from __future__ import annotations
import subprocess
import sys


def _git(args: str, cwd: str = None) -> str:
    result = subprocess.run(
        f"git {args}", shell=True, capture_output=True, text=True,
        cwd=cwd or ".",
    )
    return (result.stdout + result.stderr).strip()


# ── /commit ───────────────────────────────────────────────────────────────────

def cmd_commit(args: str, session, engine) -> str:
    """
    Stage all changes and commit with an LLM-generated message.
    Pass an explicit message to skip LLM generation:  /commit fix auth bug
    """
    cwd = session.cwd

    # Check there is something to commit
    status = _git("status --porcelain", cwd)
    if not status:
        return "Nothing to commit — working tree is clean."

    diff = _git("diff HEAD", cwd)[:6000]

    if args:
        message = args
    else:
        # Ask LLM to write the commit message
        prompt = (
            "Write a concise git commit message (imperative mood, ≤72 chars subject line, "
            "optional body after blank line) for this diff:\n\n"
            f"```diff\n{diff}\n```\n\n"
            "Output ONLY the commit message text — no quotes, no explanation."
        )
        message = engine.query(prompt, memory_ctx="")
        message = message.strip().strip('"').strip("'")

    _git("add -A", cwd)
    result = _git(f'commit -m {message!r}', cwd)
    return result


# ── /commit-push ──────────────────────────────────────────────────────────────

def cmd_commit_push(args: str, session, engine) -> str:
    """Commit (LLM message) then push to origin."""
    commit_out = cmd_commit(args, session, engine)
    if "nothing to commit" in commit_out.lower():
        return commit_out
    push_out = _git("push", session.cwd)
    return f"{commit_out}\n\n{push_out}"


# ── /push ─────────────────────────────────────────────────────────────────────

def cmd_push(args: str, session, engine) -> str:
    """Push current branch to origin (git push [args])."""
    return _git(f"push {args}", session.cwd)


# ── /diff ─────────────────────────────────────────────────────────────────────

def cmd_diff(args: str, session, engine) -> str:
    """Show git diff. Accepts standard git diff args (e.g. HEAD~1, main...HEAD)."""
    out = _git(f"diff {args}", session.cwd)
    if not out:
        return "No diff to show."
    if len(out) > 8000:
        out = out[:8000] + f"\n... [truncated — {len(out)-8000} more chars]"
    return f"```diff\n{out}\n```"


# ── /review-pr ────────────────────────────────────────────────────────────────

def cmd_review_pr(args: str, session, engine) -> str:
    """
    Review all changes since main (or a given base ref).
    /review-pr             → compare HEAD to main
    /review-pr feature/x   → compare HEAD to feature/x
    """
    base = args.strip() or "main"
    diff = _git(f"diff {base}...HEAD", session.cwd)

    if not diff:
        return f"No diff between {base} and HEAD."
    if len(diff) > 8000:
        diff = diff[:8000] + f"\n... [truncated]"

    prompt = (
        "You are doing a thorough code review of this diff.\n\n"
        "For each issue found, provide:\n"
        "  - **Verdict**: Approve / Request Changes / Reject\n"
        "  - **Severity**: Critical / High / Medium / Low\n"
        "  - **Location**: exact file + function\n"
        "  - **Issue**: what is wrong\n"
        "  - **Fix**: what to change\n\n"
        "Also note any positive patterns worth keeping.\n\n"
        f"```diff\n{diff}\n```"
    )
    return engine.query(prompt, memory_ctx="")


# ── /pr (alias) ────────────────────────────────────────────────────────────────

def cmd_pr(args: str, session, engine) -> str:
    """Alias for /review-pr."""
    return cmd_review_pr(args, session, engine)


# ── /stash ────────────────────────────────────────────────────────────────────

def cmd_stash(args: str, session, engine) -> str:
    """git stash [args]"""
    return _git(f"stash {args}", session.cwd)


# ── /log ─────────────────────────────────────────────────────────────────────

def cmd_log(args: str, session, engine) -> str:
    """Show recent git log (--oneline --graph)."""
    flags = args or "--oneline --graph -20"
    return _git(f"log {flags}", session.cwd)


# ── Registry ──────────────────────────────────────────────────────────────────

CMD_GIT: dict[str, tuple] = {
    "commit":      (cmd_commit,      "Stage all + commit (LLM message, or pass explicit)"),
    "commit-push": (cmd_commit_push, "Commit + push to origin"),
    "push":        (cmd_push,        "git push [args]"),
    "diff":        (cmd_diff,        "Show git diff [args] as fenced block"),
    "review-pr":   (cmd_review_pr,   "LLM code review of changes vs base (default: main)"),
    "pr":          (cmd_pr,          "Alias for /review-pr"),
    "stash":       (cmd_stash,       "git stash [args]"),
    "log":         (cmd_log,         "Show recent git log --oneline --graph"),
}
