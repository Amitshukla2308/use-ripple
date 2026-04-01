"""
mcp_tools.py — MCP client for calling external MCP servers over HTTP/SSE.

Wired to localhost:8002 (HyperRetrieval's FastMCP server) by default.
Also supports any external MCP server via the server_name registry.

Protocol: FastMCP exposes a streamable-HTTP transport.
  GET  /tools          → list available tools
  POST /tools/call     → call a tool  {"name": ..., "arguments": {...}}
  GET  /resources      → list resources
  GET  /resources/read → read a resource (param: uri)
"""
import json
import os
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── Server registry ───────────────────────────────────────────────────────────
# "default" points to HyperRetrieval's own MCP server.
# Agents can reference any server_name registered here.
_SERVERS: dict[str, str] = {
    "default":     os.environ.get("MCP_SERVER_URL", "http://localhost:8002"),
    "hypercode":   os.environ.get("MCP_SERVER_URL", "http://localhost:8002"),
}

_TIMEOUT = int(os.environ.get("MCP_TIMEOUT", "15"))


def _resolve_url(server_name: str) -> str:
    """Resolve a server name to a base URL."""
    name = (server_name or "default").strip().lower()
    # Direct URL passthrough
    if name.startswith("http"):
        return name.rstrip("/")
    url = _SERVERS.get(name)
    if not url:
        raise ValueError(
            f"Unknown MCP server '{server_name}'. "
            f"Known servers: {list(_SERVERS.keys())}"
        )
    return url.rstrip("/")


def _http_post(url: str, payload: dict) -> dict:
    body    = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req     = Request(url, data=body, headers=headers, method="POST")
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def _http_get(url: str, params: dict = None) -> dict:
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read().decode())


# ════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ════════════════════════════════════════════════════════════════════════════

def call_mcp_tool(server_name: str, tool_name: str, args: str) -> str:
    """
    Call a tool on an MCP server.

    args: JSON string or dict of tool arguments.
    Returns the tool result as a string.
    """
    try:
        base_url  = _resolve_url(server_name)
        arguments = json.loads(args) if isinstance(args, str) else (args or {})

        # FastMCP streamable-HTTP endpoint
        result = _http_post(
            f"{base_url}/tools/call",
            {"name": tool_name, "arguments": arguments},
        )

        # Extract content from MCP result envelope
        content = result.get("content") or result.get("result") or result
        if isinstance(content, list):
            # MCP content blocks — extract text
            texts = [
                block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            return "\n".join(texts) if texts else json.dumps(content)
        return str(content)

    except ValueError as exc:
        return f"MCP config error: {exc}"
    except (URLError, HTTPError) as exc:
        return (
            f"MCP server unreachable ({server_name} @ {_resolve_url(server_name)}): {exc}. "
            "Is the MCP server running? Try: ~/start_mcp.sh"
        )
    except Exception as exc:
        return f"MCP call error ({tool_name}): {exc}"


def list_mcp_tools(server_name: str = "default") -> str:
    """List all tools available on an MCP server."""
    try:
        base_url = _resolve_url(server_name)
        result   = _http_get(f"{base_url}/tools")

        tools = result.get("tools") or result
        if not isinstance(tools, list):
            return f"Unexpected response: {result}"

        lines = [f"Tools on '{server_name}' ({base_url}):"]
        for t in tools:
            name = t.get("name", "?")
            desc = (t.get("description") or "")[:80]
            lines.append(f"  • {name}: {desc}")
        return "\n".join(lines)

    except (URLError, HTTPError):
        return f"MCP server '{server_name}' is not reachable. Start it with ~/start_mcp.sh"
    except Exception as exc:
        return f"Error listing tools: {exc}"


def list_mcp_resources(server_name: str = "default") -> str:
    """List resources exposed by an MCP server."""
    try:
        base_url = _resolve_url(server_name)
        result   = _http_get(f"{base_url}/resources")
        resources = result.get("resources") or result
        if not isinstance(resources, list):
            return json.dumps(result, indent=2)
        if not resources:
            return f"No resources on '{server_name}'."
        lines = [f"Resources on '{server_name}':"]
        for r in resources:
            uri  = r.get("uri", "?")
            name = r.get("name", "")
            lines.append(f"  • {uri}  {name}")
        return "\n".join(lines)

    except (URLError, HTTPError):
        return f"MCP server '{server_name}' is not reachable."
    except Exception as exc:
        return f"Error listing resources: {exc}"


def read_mcp_resource(server_name: str, resource_uri: str) -> str:
    """Read a specific resource from an MCP server."""
    try:
        base_url = _resolve_url(server_name)
        result   = _http_get(f"{base_url}/resources/read", {"uri": resource_uri})
        content  = result.get("contents") or result
        if isinstance(content, list):
            return "\n".join(
                c.get("text", str(c)) for c in content
                if isinstance(c, dict)
            )
        return str(content)
    except (URLError, HTTPError):
        return f"MCP server '{server_name}' is not reachable."
    except Exception as exc:
        return f"Error reading resource: {exc}"


def mcp_register_server(name: str, url: str) -> str:
    """Register a new MCP server URL under a short name."""
    _SERVERS[name.lower()] = url.rstrip("/")
    return f"Registered MCP server '{name}' → {url}"


def mcp_auth(server_name: str, token: str) -> str:
    """
    Store an auth token for a server (prepended to future requests as Bearer header).
    Minimal stub — extend for OAuth flows.
    """
    # Store as env var pattern so _http_* can pick it up
    env_key = f"MCP_TOKEN_{server_name.upper()}"
    os.environ[env_key] = token
    return f"Auth token stored for '{server_name}' (env: {env_key})."
