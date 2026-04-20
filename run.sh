#!/bin/bash
# Wrapper script to run the Gmail MCP server with stdio transport
export MCP_TRANSPORT=stdio
cd /home/lsm/Nextcloud/mcp-server-gmail
uv run python server.py
