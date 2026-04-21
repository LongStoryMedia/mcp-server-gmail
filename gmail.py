"""Gmail API operations."""

import os
import pickle
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Self
from googleapiclient.discovery import build, Resource
from google.oauth2.credentials import Credentials
from httpx import HTTPError
from config import (
    TOKEN_FILE,
    GMAIL_TOKEN_SOURCE,
    K8S_TOKEN_MOUNT_PATH,
    K8S_TOKEN_SECRET_KEY,
    K8S_TOKEN_SECRET_NAME,
)

from pydantic import BaseModel


class MessagePartBody(BaseModel):
    attachmentId: str | None = None
    size: int
    data: str | None = None  # base64url encoded


class MessagePartHeader(BaseModel):
    name: str
    value: str


class MessagePart(BaseModel):
    partId: str | None = None
    mimeType: str | None = None
    filename: str | None = None
    headers: list[MessagePartHeader] | None = None
    body: MessagePartBody | None = None
    parts: list["MessagePart"] | None = None  # recursive for multipart


class Message(BaseModel):
    id: str
    threadId: str | None = None
    labelIds: list[str] | None = None
    snippet: str | None = None
    historyId: str | None = None
    internalDate: str | None = None  # epoch ms as string
    payload: MessagePart | None = None
    sizeEstimate: int | None = None
    raw: str | None = None  # base64url, only if format=RAW


class ListMessagesResponse(BaseModel):
    messages: list[Message] | None = None  # only id and threadId populated
    nextPageToken: str | None = None
    resultSizeEstimate: int | None = None


class ModifyMessageRequest(BaseModel):
    addLabelIds: list[str] | None = None
    removeLabelIds: list[str] | None = None


# modify response is just a full Message
ModifyMessageResponse = Message


class Label(BaseModel):
    id: str
    name: str
    type: str | None = None
    messagesTotal: int | None = None
    threadsTotal: int | None = None
    color: dict[str, str] | None = None


class CreateLabelRequest(BaseModel):
    name: str
    labelListVisibility: str
    type: str | None = None
    messagesTotal: int | None = None
    threadsTotal: int | None = None
    color: dict[str, str] | None = None


def get_credentials() -> Credentials:
    """
    Get OAuth credentials, refreshing if necessary.

    Supports two modes:
    - File mode (local dev): Uses TOKEN_FILE from config
    - K8s mode: Reads from mounted secret, updates via K8s API

    Returns valid Credentials object, handling refresh automatically.
    """
    from google.oauth2.credentials import Credentials as Oauth2Credentials
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError

    # Check if running in K8s secret mode
    use_k8s = GMAIL_TOKEN_SOURCE == "k8s"

    creds = None

    if use_k8s:
        # K8s mode: read from mounted secret
        k8s_token_path = Path(K8S_TOKEN_MOUNT_PATH) / K8S_TOKEN_SECRET_KEY
        if k8s_token_path.exists():
            with open(k8s_token_path, "rb") as token_file:
                creds = pickle.load(token_file)
    else:
        # File mode: read from local file
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "rb") as token_file:
                creds = pickle.load(token_file)

    # If no valid credentials, try to refresh
    if not creds or not creds.valid:
        if creds and creds.refresh_token:
            try:
                # Attempt to refresh the token using the stored refresh_token
                # This can succeed even if creds.expired is True
                creds.refresh(Request())
                # Save the refreshed credentials
                if use_k8s:
                    _save_k8s_token(creds)
                else:
                    with open(TOKEN_FILE, "wb") as token_file:
                        pickle.dump(creds, token_file)
                return creds
            except RefreshError:
                # Refresh token may have expired or been revoked
                pass
        raise RuntimeError(
            "Credentials are missing or invalid. Please run the authentication flow to obtain valid credentials."
        )

    return creds


def _save_k8s_token(creds: Credentials) -> None:
    """
    Save refreshed token to K8s secret.
    Updates the mounted secret file and patches the K8s secret.
    """
    import base64
    import subprocess

    k8s_token_path = Path(K8S_TOKEN_MOUNT_PATH) / K8S_TOKEN_SECRET_KEY

    # Write to mounted path (if writable)
    try:
        with open(k8s_token_path, "wb") as f:
            pickle.dump(creds, f)
    except (OSError, PermissionError):
        pass  # Mounted secrets are often read-only

    # Try to patch the K8s secret via kubectl
    try:
        # Create temp file with updated token
        import tempfile
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as tmp:
            pickle.dump(creds, tmp)
            tmp_path = tmp.name

        # Update secret using kubectl
        result = subprocess.run(
            [
                "kubectl", "patch", "secret", K8S_TOKEN_SECRET_NAME,
                "-n", os.environ.get("POD_NAMESPACE", "llmmllab-mcp"),
                "-p", f'{{"data":{{"{K8S_TOKEN_SECRET_KEY}": "{base64.b64encode(open(tmp_path, "rb").read()).decode()}"}}}}',
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Patch failed - may not have kubectl or permissions
            pass

        # Clean up temp file
        import os as _os
        _os.unlink(tmp_path)
    except Exception:
        # Silently ignore - token refresh still works, just won't persist to K8s secret
        pass


class GmailService:
    """Context manager for Gmail API service."""

    def __enter__(self) -> Self:
        self.creds = get_credentials()
        self.service = build("gmail", "v1", credentials=self.creds)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.service.close()

    def get_messages(
        self,
        query: str,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> ListMessagesResponse:
        """Helper to list messages with pagination."""
        try:
            raw = (
                self.service.users()  # pylint: disable=no-member  type: ignore
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            )
            response = ListMessagesResponse.model_validate(raw)
            return response
        except HTTPError as e:
            raise RuntimeError(f"Gmail API error: {e}") from e

    def get_message(self, msg_id: str) -> Message:
        """Get full message details by ID."""
        try:
            raw = (
                self.service.users()  # pylint: disable=no-member  type: ignore
                .messages()
                .get(userId="me", id=msg_id)
                .execute()
            )
            message = Message.model_validate(raw)
            return message
        except HTTPError as e:
            raise RuntimeError(f"Gmail API error: {e}") from e

    def list_labels(self) -> list[Label]:
        """List all labels for the user."""
        try:
            raw = (
                self.service.users()  # pylint: disable=no-member  type: ignore
                .labels()
                .list(userId="me")
                .execute()
            )
            labels_data = raw.get("labels", [])
            return [Label.model_validate(label) for label in labels_data]
        except HTTPError as e:
            raise RuntimeError(f"Gmail API error: {e}") from e

    def get_label_by_name(self, label_name: str) -> Label | None:
        """Get a label by name, returns None if not found."""
        labels = self.list_labels()
        for label in labels:
            if label.name.lower() == label_name.lower():
                return label
        return None

    def create_label(
        self, label_name: str, color: str | None = None
    ) -> Label:
        """Create a new label with optional color."""
        body: dict[str, str] = {
            "name": label_name,
            "labelListVisibility": "labelShow",
        }

        # Map color names to Gmail color IDs
        color_map = {
            "yellow": "colorYellow",
            "blue": "colorBlue",
            "green": "colorGreen",
            "red": "colorRed",
            "orange": "colorOrange",
            "purple": "colorPurple",
        }

        if color and color in color_map:
            body["color"] = color_map[color]

        try:
            raw = (
                self.service.users()  # pylint: disable=no-member  type: ignore
                .labels()
                .create(userId="me", body=body)
                .execute()
            )
            return Label.model_validate(raw)
        except HTTPError as e:
            raise RuntimeError(f"Gmail API error: {e}") from e

    def get_or_create_label(
        self, label_name: str, color: str | None = None
    ) -> Label:
        """Get existing label or create a new one."""
        existing = self.get_label_by_name(label_name)
        if existing:
            return existing
        return self.create_label(label_name, color)

    def modify_messages(
        self, message_ids: list[str], add_label_ids: list[str] | None = None
    ) -> int:
        """Add labels to messages. Returns count of successfully modified messages."""
        modified = 0
        messages_api = self.service.users().messages()  # type: ignore
        for msg_id in message_ids:
            try:
                body: dict[str, list[str]] = {}
                if add_label_ids:
                    body["addLabelIds"] = add_label_ids

                messages_api.modify(userId="me", id=msg_id, body=body).execute()
                modified += 1
            except HTTPError:
                continue
        return modified

    def trash_messages(self, message_ids: list[str]) -> int:
        """Move messages to trash by ID. Returns count of successfully trashed messages."""
        trashed = 0
        messages_api = self.service.users().messages()  # type: ignore
        for msg_id in message_ids:
            try:
                messages_api.trash(userId="me", id=msg_id).execute()
                trashed += 1
            except HTTPError:
                continue
        return trashed
