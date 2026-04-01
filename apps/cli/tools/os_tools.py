"""
os_tools.py — Advanced OS interoperability tools.
"""

import subprocess
import os

def run_powershell(command: str) -> str:
    """Run a PowerShell specific command block."""
    if os.name != 'nt':
        return "PowerShell is primarily for Windows environments."
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=60
        )
        return (proc.stdout + "\n" + proc.stderr).strip() or "Success. No output."
    except Exception as e:
        return f"PowerShell execution failed: {e}"

def start_repl(script: str, lang: str = "python") -> str:
    """Execute code inside an interactive-like REPL block."""
    try:
        if lang == "python":
            proc = subprocess.run(["python3", "-c", script], capture_output=True, text=True, timeout=30)
        elif lang == "node":
            proc = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
        else:
            return f"Unsupported REPL language: {lang}"
        return (proc.stdout + "\n" + proc.stderr).strip() or "Script executed successfully."
    except Exception as e:
        return f"REPL failed: {e}"

def lsp_query(file_path: str, line: int, char: int) -> str:
    """Stub for Language Server Protocol 'Hover' query."""
    return f"LSP Definition for {file_path}:{line}:{char} (Stub: Not connected to an active LSP handle)"
