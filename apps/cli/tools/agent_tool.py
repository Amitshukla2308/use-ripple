"""
agent_tool.py — Sub-agent tool.

Spawns a child QueryEngine instance to handle a focused subtask.
Equivalent to codetoolcli's AgentTool — runs a bounded nested ReAct loop.

Use when: a task has a well-scoped sub-problem that can run independently
(e.g. "find all callers of X and summarise them", "read and summarise file Y").
"""
import pathlib
import sys


def run_agent(prompt: str, system_context: str = "") -> str:
    """
    Delegate a focused subtask to a child QueryEngine.
    Returns the child's synthesized answer (capped at 10 tool calls).
    """
    _cli_dir = pathlib.Path(__file__).parent.parent
    if str(_cli_dir) not in sys.path:
        sys.path.insert(0, str(_cli_dir))

    try:
        from engine import QueryEngine  # type: ignore
        child = QueryEngine(
            max_tool_calls=10,
            extra_system=system_context,
            verbose=False,
            streaming=False,
        )
        return child.query(prompt)
    except Exception as exc:
        return f"Sub-agent error: {exc}"


import json
import os

_AGENT_STATE_FILE = ".files/agents_state.json"

def _load_agent_state() -> dict:
    if os.path.exists(_AGENT_STATE_FILE):
        with open(_AGENT_STATE_FILE, "r") as f:
            return json.load(f)
    return {"teams": {}, "messages": {}}

def _save_agent_state(state: dict):
    os.makedirs(os.path.dirname(_AGENT_STATE_FILE), exist_ok=True)
    with open(_AGENT_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def create_team(team_name: str, objective: str, members: list) -> str:
    state = _load_agent_state()
    if team_name in state["teams"]:
        return f"Team '{team_name}' already exists."
    state["teams"][team_name] = {"objective": objective, "members": members}
    _save_agent_state(state)
    return f"Team '{team_name}' created successfully with {len(members)} members."

def delete_team(team_name: str) -> str:
    state = _load_agent_state()
    if team_name not in state["teams"]:
        return f"Team '{team_name}' not found."
    del state["teams"][team_name]
    _save_agent_state(state)
    return f"Team '{team_name}' deleted."

def send_message(recipient: str, message: str) -> str:
    state = _load_agent_state()
    if recipient not in state["messages"]:
        state["messages"][recipient] = []
    state["messages"][recipient].append(message)
    _save_agent_state(state)
    return f"Message sent to {recipient}."
