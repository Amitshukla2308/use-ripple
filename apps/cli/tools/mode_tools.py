"""
mode_tools.py — Manage interaction and planning contexts.
"""

# We track mode dynamically in memory. If this was a full integration it would
# update the context within the actual Chat loop handling system prompts.
_PLAN_MODE_ENABLED = False

def enter_plan_mode() -> str:
    """Pause destructive actions and enter structured plan execution mode."""
    global _PLAN_MODE_ENABLED
    _PLAN_MODE_ENABLED = True
    return "Plan Mode enabled. All destructive actions will be explicitly validated."

def exit_plan_mode() -> str:
    """Exit plan mode and return to standard prompt."""
    global _PLAN_MODE_ENABLED
    _PLAN_MODE_ENABLED = False
    return "Plan Mode disabled. Returning to auto-execution."

def write_todo(todo: str) -> str:
    """Store a simple memory string in a persistent context file."""
    with open(".files/memory.md", "a") as f:
        f.write(f"- [ ] {todo}\n")
    return f"Listed to-do item."

def generate_brief(topic: str) -> str:
    """Synthesize a quick overview. Usually delegates to the LLM summarizing the context block."""
    return f"Brief requested for {topic}. Context will guide this block."

def export_synthetic_output(payload: str, path: str) -> str:
    """Write structured json/xml output to path safely."""
    with open(path, "w") as f:
        f.write(payload)
    return f"Synthetic output exported to {path}."

def ask_user_question(question: str) -> str:
    """Interrupt the tool loop and ask the user a specific question."""
    # In a UI based agent, this yields execution. Stub for now.
    return f"Question marked for user interruption: '{question}'"
