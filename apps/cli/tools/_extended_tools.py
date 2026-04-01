"""
_extended_tools.py — extended tool schemas bridging codetoolcli capabilities into the python stack.
"""

from .agent_tool import create_team, delete_team, send_message
from .task_tools import create_task, get_task, list_tasks, update_task, stop_task, set_task_output
from .web_tools import web_search, web_fetch
from .mcp_tools import call_mcp_tool, list_mcp_resources, read_mcp_resource, mcp_auth
from .os_tools import run_powershell, start_repl, lsp_query
from .mode_tools import enter_plan_mode, exit_plan_mode, write_todo, generate_brief, export_synthetic_output, ask_user_question
from .git_tools import enter_worktree, exit_worktree
from .time_tools import run_sleep, schedule_cron, trigger_remote

EXTENDED_TOOL_SCHEMAS = [
    # Agent Tools
    {"type": "function", "function": {"name": "create_team", "description": "Create an orchestration team.", "parameters": {"type": "object", "properties": {"team_name": {"type": "string"}, "objective": {"type": "string"}, "members": {"type": "array", "items": {"type": "string"}}}, "required": ["team_name", "objective", "members"]}}},
    {"type": "function", "function": {"name": "delete_team", "description": "Delete an orchestration team.", "parameters": {"type": "object", "properties": {"team_name": {"type": "string"}}, "required": ["team_name"]}}},
    {"type": "function", "function": {"name": "send_message", "description": "Send an asynchronous message.", "parameters": {"type": "object", "properties": {"recipient": {"type": "string"}, "message": {"type": "string"}}, "required": ["recipient", "message"]}}},

    # Task Tools
    {"type": "function", "function": {"name": "create_task", "description": "Create tracking task.", "parameters": {"type": "object", "properties": {"description": {"type": "string"}, "assignee": {"type": "string"}}, "required": ["description"]}}},
    {"type": "function", "function": {"name": "get_task", "description": "Get task details.", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}}},
    {"type": "function", "function": {"name": "list_tasks", "description": "List all active tracking tasks.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "update_task", "description": "Update task status.", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "status": {"type": "string"}}, "required": ["task_id", "status"]}}},
    {"type": "function", "function": {"name": "stop_task", "description": "Stop active task.", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}}},
    {"type": "function", "function": {"name": "set_task_output", "description": "Finalize task.", "parameters": {"type": "object", "properties": {"task_id": {"type": "string"}, "output": {"type": "string"}}, "required": ["task_id", "output"]}}},

    # Web Tools
    {"type": "function", "function": {"name": "web_search", "description": "Search web using DDG.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "web_fetch", "description": "Fetch text structure from URL.", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},

    # MCP Tolls
    {"type": "function", "function": {"name": "call_mcp_tool", "description": "Call an external MCP server tool.", "parameters": {"type": "object", "properties": {"server_name": {"type": "string"}, "tool_name": {"type": "string"}, "args": {"type": "string"}}, "required": ["server_name", "tool_name", "args"]}}},
    {"type": "function", "function": {"name": "list_mcp_resources", "description": "List remote MCP resources.", "parameters": {"type": "object", "properties": {"server_name": {"type": "string"}}, "required": ["server_name"]}}},
    {"type": "function", "function": {"name": "read_mcp_resource", "description": "Read specific MCP resource.", "parameters": {"type": "object", "properties": {"server_name": {"type": "string"}, "resource_uri": {"type": "string"}}, "required": ["server_name", "resource_uri"]}}},
    {"type": "function", "function": {"name": "mcp_auth", "description": "Authenticate to MCP.", "parameters": {"type": "object", "properties": {"server_name": {"type": "string"}, "token": {"type": "string"}}, "required": ["server_name", "token"]}}},

    # OS Tools
    {"type": "function", "function": {"name": "run_powershell", "description": "Run powershell command natively", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "start_repl", "description": "Launch REPL execution block.", "parameters": {"type": "object", "properties": {"script": {"type": "string"}, "lang": {"type": "string"}}, "required": ["script"]}}},
    {"type": "function", "function": {"name": "lsp_query", "description": "LSP hover command.", "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "line": {"type": "integer"}, "char": {"type": "integer"}}, "required": ["file_path", "line", "char"]}}},

    # Mode Tools
    {"type": "function", "function": {"name": "enter_plan_mode", "description": "Enter defensive execution mode.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "exit_plan_mode", "description": "Exit plan mode.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "write_todo", "description": "Save action plan to persistent todo memory.", "parameters": {"type": "object", "properties": {"todo": {"type": "string"}}, "required": ["todo"]}}},
    {"type": "function", "function": {"name": "generate_brief", "description": "Synthesize context.", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]}}},
    {"type": "function", "function": {"name": "export_synthetic_output", "description": "Save structure to file safely.", "parameters": {"type": "object", "properties": {"payload": {"type": "string"}, "path": {"type": "string"}}, "required": ["payload", "path"]}}},
    {"type": "function", "function": {"name": "ask_user_question", "description": "Wait for user confirmation.", "parameters": {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]}}},

    # Git
    {"type": "function", "function": {"name": "enter_worktree", "description": "Isolate repository operation.", "parameters": {"type": "object", "properties": {"branch": {"type": "string"}}, "required": ["branch"]}}},
    {"type": "function", "function": {"name": "exit_worktree", "description": "Tear down isolation worktree.", "parameters": {"type": "object", "properties": {}}}},

    # Time
    {"type": "function", "function": {"name": "run_sleep", "description": "Block until N seconds pass.", "parameters": {"type": "object", "properties": {"seconds": {"type": "integer"}}, "required": ["seconds"]}}},
    {"type": "function", "function": {"name": "schedule_cron", "description": "Run function async regularly.", "parameters": {"type": "object", "properties": {"schedule": {"type": "string"}, "command": {"type": "string"}}, "required": ["schedule", "command"]}}},
    {"type": "function", "function": {"name": "trigger_remote", "description": "Trigger remote systems over HTTP.", "parameters": {"type": "object", "properties": {"endpoint": {"type": "string"}, "payload": {"type": "string"}}, "required": ["endpoint", "payload"]}}}
]

EXTENDED_DISPATCH = {
    # Agent
    "create_team": lambda a: create_team(a.get("team_name"), a.get("objective"), a.get("members")),
    "delete_team": lambda a: delete_team(a.get("team_name")),
    "send_message": lambda a: send_message(a.get("recipient"), a.get("message")),

    # Task
    "create_task": lambda a: create_task(a.get("description"), a.get("assignee", "agent")),
    "get_task": lambda a: get_task(a.get("task_id")),
    "list_tasks": lambda a: list_tasks(),
    "update_task": lambda a: update_task(a.get("task_id"), a.get("status")),
    "stop_task": lambda a: stop_task(a.get("task_id")),
    "set_task_output": lambda a: set_task_output(a.get("task_id"), a.get("output")),

    # Web
    "web_search": lambda a: web_search(a.get("query")),
    "web_fetch": lambda a: web_fetch(a.get("url")),

    # MCP
    "call_mcp_tool": lambda a: call_mcp_tool(a.get("server_name"), a.get("tool_name"), a.get("args")),
    "list_mcp_resources": lambda a: list_mcp_resources(a.get("server_name")),
    "read_mcp_resource": lambda a: read_mcp_resource(a.get("server_name"), a.get("resource_uri")),
    "mcp_auth": lambda a: mcp_auth(a.get("server_name"), a.get("token")),

    # OS
    "run_powershell": lambda a: run_powershell(a.get("command")),
    "start_repl": lambda a: start_repl(a.get("script"), a.get("lang")),
    "lsp_query": lambda a: lsp_query(a.get("file_path"), a.get("line"), a.get("char")),

    # Mode
    "enter_plan_mode": lambda a: enter_plan_mode(),
    "exit_plan_mode": lambda a: exit_plan_mode(),
    "write_todo": lambda a: write_todo(a.get("todo")),
    "generate_brief": lambda a: generate_brief(a.get("topic")),
    "export_synthetic_output": lambda a: export_synthetic_output(a.get("payload"), a.get("path")),
    "ask_user_question": lambda a: ask_user_question(a.get("question")),

    # Git
    "enter_worktree": lambda a: enter_worktree(a.get("branch")),
    "exit_worktree": lambda a: exit_worktree(),

    # Time
    "run_sleep": lambda a: run_sleep(a.get("seconds")),
    "schedule_cron": lambda a: schedule_cron(a.get("schedule"), a.get("command")),
    "trigger_remote": lambda a: trigger_remote(a.get("endpoint"), a.get("payload"))
}
