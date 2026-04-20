"""
Server code for FastMCP Gmail integration.
This server listens for MCP requests and processes them using the FastMCP framework.
It is designed to run in a Docker container and can be configured using environment variables.
"""

import os
import sys
import time
from typing import Any
from httpx import HTTPError
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# Get or create the shared mcp object
# Use sys.modules to ensure the same instance across different import contexts
def _get_mcp():
    """Lazy initialization of mcp to ensure single instance."""
    if "_gmail_mcp_instance" not in sys.modules:
        mcp_server_base_url = os.environ.get("MCP_SERVER_BASE_URL")
        if mcp_server_base_url:
            from oauth_provider import create_oauth_provider
            auth = create_oauth_provider()
            sys.modules["_gmail_mcp_instance"] = FastMCP("gmail", auth=auth)
        else:
            sys.modules["_gmail_mcp_instance"] = FastMCP("gmail", auth=None)
    return sys.modules["_gmail_mcp_instance"]

mcp = _get_mcp()

# Import GmailService for tool implementations
from gmail import GmailService


# Tool: read_email
@mcp.tool(
    name="read_email",
    description="Read a full email by ID and return sender, subject, date, and HTML/text body.",
)
def read_email_impl(message_id: str) -> dict[str, Any]:
    """Read a full email by ID."""
    with GmailService() as service:
        message = service.get_message(message_id)

        # Extract headers
        headers = {}
        sender = ""
        subject = ""
        date = ""
        if message.payload and message.payload.headers:
            for h in message.payload.headers:
                headers[h.name.lower()] = h.value
                if h.name.lower() == "from":
                    sender = h.value
                elif h.name.lower() == "subject":
                    subject = h.value
                elif h.name.lower() == "date":
                    date = h.value

        # Extract body text and HTML
        def extract_body(part):
            html = ""
            text = ""
            if part.body and part.body.data:
                import base64
                try:
                    decoded = base64.urlsafe_b64decode(part.body.data).decode("utf-8", errors="replace")
                    if part.mimeType == "text/html":
                        html = decoded
                    elif part.mimeType == "text/plain":
                        text = decoded
                except Exception:
                    pass
            if part.parts:
                for p in part.parts:
                    h, t = extract_body(p)
                    html = html or h
                    text = text or t
            return html, text

        html_body, text_body = "", ""
        if message.payload:
            html_body, text_body = extract_body(message.payload)

        return {
            "id": message.id,
            "sender": sender,
            "subject": subject,
            "date": date,
            "html": html_body,
            "text": text_body,
        }



# Tool: grep_email
@mcp.tool(
    name="grep_email",
    description="Search email bodies for a pattern. Returns matching emails with context lines before and after the match (like grep -C).",
)
def grep_email_impl(query: str, pattern: str, max_results: int = 10, context: int = 2) -> list[dict[str, Any]]:
    """Search email bodies for a pattern match with context lines."""
    import re
    results = []
    page_token = None

    with GmailService() as service:
        count = 0
        while count < max_results:
            try:
                msgRes = service.get_messages(query=query, page_token=page_token, max_results=100)
            except HTTPError:
                break

            messages = msgRes.messages or []
            for msg in messages:
                if count >= max_results:
                    break
                message = service.get_message(msg.id)

                # Extract body text
                def extract_body(part):
                    text = ""
                    if part.body and part.body.data:
                        import base64
                        try:
                            decoded = base64.urlsafe_b64decode(part.body.data).decode("utf-8", errors="replace")
                            if part.mimeType == "text/plain":
                                text = decoded
                        except Exception:
                            pass
                    if part.parts:
                        for p in part.parts:
                            t = extract_body(p)
                            text = text or t
                    return text

                body_text = ""
                if message.payload:
                    body_text = extract_body(message.payload)

                # Search for pattern in body
                if re.search(pattern, body_text, re.IGNORECASE):
                    # Extract headers
                    sender = ""
                    subject = ""
                    if message.payload and message.payload.headers:
                        for h in message.payload.headers:
                            if h.name.lower() == "from":
                                sender = h.value
                            elif h.name.lower() == "subject":
                                subject = h.value

                    # Find matching lines with context (like grep -C)
                    lines = body_text.split("\n")
                    match_indices = set()
                    for i, line in enumerate(lines):
                        if re.search(pattern, line, re.IGNORECASE):
                            for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                                match_indices.add(j)

                    matches = []
                    for i in sorted(match_indices):
                        line = lines[i]
                        prefix = "  "
                        if re.search(pattern, line, re.IGNORECASE):
                            prefix = ">>"
                        matches.append(f"{prefix} {line}")

                    results.append({
                        "id": message.id,
                        "sender": sender,
                        "subject": subject,
                        "matches": matches,
                    })
                    count += 1

            page_token = msgRes.nextPageToken
            if not page_token:
                break

    return results

# Tool: count_emails
@mcp.tool(
    name="count_emails",
    description="Count the number of emails in the inbox with optional filtering.",
)
def count_emails_impl(query: str) -> int:
    """Count emails matching the query."""
    total_count = 0
    page_token = None

    with GmailService() as service:
        while True:
            try:
                msgRes = service.get_messages(query=query, page_token=page_token, max_results=100)
            except HTTPError as e:
                if "429" in str(e) and total_count == 0:
                    time.sleep(1)
                    continue
                raise

            messages = msgRes.messages or []
            total_count += len(messages)

            page_token = msgRes.nextPageToken
            if not page_token:
                break

    return total_count


# Tool: search_emails
@mcp.tool(
    name="search_emails",
    description="Search for emails in the inbox with optional filtering.",
)
def search_emails_impl(query: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Search for emails and return details."""
    results = []
    page_token = None

    with GmailService() as service:
        count = 0
        while count < max_results:
            try:
                msgRes = service.get_messages(query=query, page_token=page_token, max_results=100)
            except HTTPError:
                break

            messages = msgRes.messages or []
            for msg in messages:
                if count >= max_results:
                    break
                message = service.get_message(msg.id)
                results.append({
                    "id": message.id,
                    "snippet": message.snippet,
                    "labels": message.labelIds or [],
                })
                count += 1

            page_token = msgRes.nextPageToken
            if not page_token:
                break

    return results


# Tool: delete_emails
@mcp.tool(
    name="delete_emails",
    description="Delete emails matching the query.",
)
def delete_emails_impl(query: str, max_results: int = 100, dry_run: bool = False) -> dict[str, Any]:
    """Delete emails matching the query."""
    message_ids = []
    page_token = None

    with GmailService() as service:
        while len(message_ids) < max_results:
            try:
                msgRes = service.get_messages(query=query, page_token=page_token, max_results=100)
            except HTTPError:
                break

            messages = msgRes.messages or []
            message_ids.extend([m.id for m in messages])

            page_token = msgRes.nextPageToken
            if not page_token or len(message_ids) >= max_results:
                break

        if not message_ids:
            return {"found": 0, "deleted": 0, "message": "No emails found"}

        if dry_run:
            return {"found": len(message_ids), "deleted": 0, "dry_run": True, "ids": message_ids[:10]}

        trashed = service.trash_messages(message_ids)
        return {"found": len(message_ids), "trashed": trashed, "dry_run": False}


# Tool: add_label_to_emails
@mcp.tool(
    name="add_label_to_emails",
    description="Add a label to emails matching the query.",
)
def add_label_to_emails_impl(query: str, label_name: str, max_results: int = 100) -> dict[str, Any]:
    """Add a label to emails matching the query."""
    with GmailService() as service:
        label = service.get_or_create_label(label_name)

        message_ids = []
        page_token = None

        while len(message_ids) < max_results:
            try:
                msgRes = service.get_messages(query=query, page_token=page_token, max_results=100)
            except HTTPError:
                break

            messages = msgRes.messages or []
            message_ids.extend([m.id for m in messages])

            page_token = msgRes.nextPageToken
            if not page_token or len(message_ids) >= max_results:
                break

        if not message_ids:
            return {"found": 0, "labeled": 0, "message": "No emails found"}

        labeled = service.modify_messages(message_ids, add_label_ids=[label.id])
        return {"found": len(message_ids), "labeled": labeled, "label": label_name}


# Tool: get_or_create_label
@mcp.tool(
    name="get_or_create_label",
    description="Get a label ID or create it if it doesn't exist.",
)
def get_or_create_label_impl(label_name: str, color: str | None = None) -> dict[str, Any]:
    """Get label ID or create label if it doesn't exist."""
    with GmailService() as service:
        label = service.get_or_create_label(label_name, color)
        return {"id": label.id, "name": label.name, "color": label.color}


# Tool: create_label
@mcp.tool(
    name="create_label",
    description="Create a new Gmail label.",
)
def create_label_impl(label_name: str, color: str | None = None) -> dict[str, Any]:
    """Create a new Gmail label."""
    with GmailService() as service:
        label = service.create_label(label_name, color)
        return {"id": label.id, "name": label.name, "color": label.color}


# Tool: list_labels
@mcp.tool(
    name="list_labels",
    description="List all labels in the Gmail account.",
)
def list_labels_impl() -> list[dict[str, Any]]:
    """List all labels in the Gmail account."""
    with GmailService() as service:
        labels = service.list_labels()
        return [{"id": label.id, "name": label.name, "color": label.color} for label in labels]


# Custom routes for OAuth discovery
@mcp.custom_route("/mcp/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_discovery_mcp(request: Request):
    """Return JSON 404 for OAuth discovery at /mcp/.well-known."""
    return JSONResponse(status_code=404, content={"error": "oauth_not_configured", "message": "OAuth is not configured"})


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_discovery_root(request: Request):
    """Return JSON 404 for OAuth discovery at root."""
    return JSONResponse(status_code=404, content={"error": "oauth_not_configured", "message": "OAuth is not configured"})


@mcp.custom_route("/mcp/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_mcp(request: Request):
    """Return JSON 404 for OAuth protected resource at /mcp/.well-known."""
    return JSONResponse(status_code=404, content={"error": "oauth_not_configured", "message": "OAuth is not configured"})


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def oauth_protected_root(request: Request):
    """Return JSON 404 for OAuth protected resource at root."""
    return JSONResponse(status_code=404, content={"error": "oauth_not_configured", "message": "OAuth is not configured"})


# Check transport mode via environment variable
transport_mode = os.environ.get("MCP_TRANSPORT", "http")

if transport_mode == "stdio":
    mcp.run(transport="stdio")
else:
    mcp.run(transport="http", host="0.0.0.0", port=8000)
