# PyPI Publish Guide

Package: `ripple-mcp` v0.6.0  
Build: `ripple_mcp-0.6.0-py3-none-any.whl` (pre-built in `dist/`)

Note: `ripple` is taken on PyPI (v0.0.1, unrelated project). `ripple-mcp` is available — verified 2026-04-18.

## One-command publish (once Amit provides token)

```bash
cd ~/projects/hyperretrieval

# Step 1: Install twine if needed
/home/beast/miniconda3/bin/pip install twine

# Step 2: Rebuild wheel if code changed since last build
cd /tmp && /home/beast/miniconda3/bin/python3 -m build /home/beast/projects/hyperretrieval --wheel --no-isolation
# wheel lands in ~/projects/hyperretrieval/dist/ automatically

# Step 3: Upload
cd ~/projects/hyperretrieval
/home/beast/miniconda3/bin/python3 -m twine upload dist/ripple_mcp-0.6.0-py3-none-any.whl \
  --username __token__ \
  --password <PYPI_TOKEN_HERE>
```

## After publish

1. Verify: `pip install ripple-mcp` on a clean machine
2. Update `.mcp-registry/server.json` — set `install.pip` to `ripple-mcp`
3. Submit MCP Registry PR (GitHub Copilot + Cursor marketplaces)

## Users install with

```bash
pip install ripple-mcp
ripple --help
```

## Name availability (checked 2026-04-18)

| Name | Status |
|------|--------|
| `ripple` | TAKEN (v0.0.1, unrelated) |
| `ripple-mcp` | **AVAILABLE** ← use this |
| `ripple-code` | available |
| `coderipple` | available |
| `hyperripple` | available |
| `hr-mcp` | available |
