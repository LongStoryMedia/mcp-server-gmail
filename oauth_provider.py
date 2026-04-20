"""
OAuth provider configuration for Gmail MCP Server using Dex as the identity provider.

This module sets up OAuthProxy to work with the existing Dex infrastructure.

Dex's issuer (public URL used in JWT tokens) differs from the internal k8s
service URL.  The browser-facing authorization endpoint must use the public
issuer so the user's browser can reach Dex.  The token and JWKS endpoints are
called server-to-server and should use the in-cluster DNS name.
"""

import os
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier


def create_oauth_provider() -> OAuthProxy:
    """
    Create an OAuthProxy configured to work with Dex.

    Environment variables:
        DEX_ISSUER          – Dex's public issuer URL (matches `issuer` in dex config.yaml).
                              Used for the authorization endpoint (browser redirect) and
                              JWT issuer validation.
        DEX_INTERNAL_URL    – In-cluster URL for server-to-server calls (token exchange,
                              JWKS fetching).
        MCP_SERVER_BASE_URL – Public URL of this MCP server.
        OAUTH_CLIENT_ID     – Dex static client id.
        OAUTH_JWT_SIGNING_KEY – Secret for signing FastMCP-issued JWTs (required when
                                the Dex client is public / has no secret).
    """
    # Public issuer URL (must match Dex config.yaml `issuer`).
    # The user's browser is redirected here for login.
    dex_issuer = os.environ.get("DEX_ISSUER", "https://auth.longstorymedia.com")

    # Internal k8s service URL for server-to-server communication.
    dex_internal = os.environ.get(
        "DEX_INTERNAL_URL", "http://dex.auth.svc.cluster.local:5556"
    )

    base_url = os.environ.get("MCP_SERVER_BASE_URL", "http://localhost:8000")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "gmail-mcp-client")
    jwt_signing_key = os.environ.get("OAUTH_JWT_SIGNING_KEY")

    if not jwt_signing_key:
        raise RuntimeError(
            "OAUTH_JWT_SIGNING_KEY must be set (required for public Dex clients "
            "that have no client_secret)"
        )

    # Validate upstream tokens (Dex JWTs) using the internal JWKS endpoint
    # but matching the public issuer claim.
    token_verifier = JWTVerifier(
        jwks_uri=f"{dex_internal}/keys",
        issuer=dex_issuer,
        audience=client_id,
    )

    auth = OAuthProxy(
        # Browser-facing: user's browser is redirected to the public Dex URL
        upstream_authorization_endpoint=f"{dex_issuer}/auth",
        # Server-to-server: exchange auth code for tokens via internal URL
        upstream_token_endpoint=f"{dex_internal}/token",
        upstream_client_id=client_id,
        # Public client – no secret sent to Dex
        token_endpoint_auth_method="none",
        token_verifier=token_verifier,
        base_url=base_url,
        # Required because there is no upstream_client_secret to derive from
        jwt_signing_key=jwt_signing_key,
        allowed_client_redirect_uris=[
            "http://localhost:*",
            "http://127.0.0.1:*",
        ],
    )

    return auth
