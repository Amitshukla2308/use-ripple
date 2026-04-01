"""
task_tools.py — Task management tools.
"""

import json
import os
import uuid
from datetime import datetime

_TASK_STATE_FILE = ".files/tasks_state.json"

def _load_tasks() -> dict:
    if os.path.exists(_TASK_STATE_FILE):
        with open(_TASK_STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def _save_tasks(state: dict):
    os.makedirs(os.path.dirname(_TASK_STATE_FILE), exist_ok=True)
    with open(_TASK_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def create_task(description: str, assignee: str = "agent") -> str:
    state = _load_tasks()
    task_id = str(uuid.uuid4())[:8]
    state[task_id] = {
        "description": description,
        "assignee": assignee,
        "status": "pending",
        "output": "",
        "created_at": str(datetime.now())
    }
    _save_tasks(state)
    return f"Task created: {task_id}"

def get_task(task_id: str) -> str:
    state = _load_tasks()
    task = state.get(task_id)
    if not task:
        return f"Task {task_id} not found."
    return json.dumps(task, indent=2)

def list_tasks() -> str:
    state = _load_tasks()
    if not state:
        return "No tasks found."
    lines = []
    for tid, t in state.items():
        lines.append(f"[{tid}] {t['status']} - {t['description'][:50]} (assignee: {t['assignee']})")
    return "\n".join(lines)

def update_task(task_id: str, status: str) -> str:
    state = _load_tasks()
    if task_id not in state:
        return f"Task {task_id} not found."
    state[task_id]["status"] = status
    _save_tasks(state)
    return f"Task {task_id} updated to {status}."

def stop_task(task_id: str) -> str:
    return update_task(task_id, "stopped")

def set_task_output(task_id: str, output: str) -> str:
    state = _load_tasks()
    if task_id not in state:
        return f"Task {task_id} not found."
    state[task_id]["output"] = output
    state[task_id]["status"] = "completed"
    _save_tasks(state)
    return f"Task {task_id} output saved and market as completed."
