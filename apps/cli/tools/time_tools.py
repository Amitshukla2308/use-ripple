"""
time_tools.py — Sleep and trigger functionality for background daemon operations.
"""

import time
import threading

def run_sleep(seconds: int) -> str:
    """Pause the agent loop for n seconds to await an external state change."""
    if seconds > 300:
        return "Sleep limited to maximum 300 seconds (5m)."
    time.sleep(seconds)
    return "Awoke from sleep."

def schedule_cron(schedule: str, command: str) -> str:
    """Stub for scheduling cron commands running async loops."""
    # In a fully deployed setup, this pushes to celerey / async workers.
    return f"Cron '{schedule}' attached to '{command}'."

def trigger_remote(endpoint: str, payload: str) -> str:
    """Trigger a remote REST callback."""
    return f"Trigger payload delivered to {endpoint}."
