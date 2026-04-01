"""
git_tools.py — Worktree isolation functionality using the git cli.
"""

import subprocess
import os

_ORIGINAL_CWD = os.getcwd()
_ACTIVE_WORKTREE = None

def enter_worktree(branch: str, directory_path: str = None) -> str:
    """Create a new worktree isolating changes without destroying the main tree context."""
    global _ACTIVE_WORKTREE
    if _ACTIVE_WORKTREE:
        return f"Already in a worktree: {_ACTIVE_WORKTREE}. Use exit_worktree first."
        
    wt_path = directory_path or f".git/wt_{branch}"
    try:
        proc = subprocess.run(
            ["git", "worktree", "add", wt_path, branch],
            capture_output=True, text=True, check=True
        )
        os.chdir(wt_path)
        _ACTIVE_WORKTREE = wt_path
        return f"Worktree initialized and active at {wt_path} on branch {branch}."
    except Exception as e:
        return f"Git worktree failed: {e}"

def exit_worktree(destroy: bool = True) -> str:
    """Return back to main repo state and optionally teardown worktree."""
    global _ACTIVE_WORKTREE
    if not _ACTIVE_WORKTREE:
        return "No active worktree to exit."
    try:
        os.chdir(_ORIGINAL_CWD)
        wt = _ACTIVE_WORKTREE
        _ACTIVE_WORKTREE = None
        if destroy:
            proc = subprocess.run(
                ["git", "worktree", "remove", "-f", wt],
                capture_output=True, text=True, check=True
            )
            return "Returned to base, worktree destroyed."
        return "Returned to base, worktree persisted."
    except Exception as e:
        return f"Error exiting worktree: {e}"
