"""
OAuth provider configuration for Gmail MCP Server using Dex as the identity provider.

This module sets up OAuthProxy to work with the existing Dex infrastructure
at https://auth.longstorymedia.com
"""

import os
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl


def create_oauth_provider() -> OAuthProxy:
    """
    Create an OAuthProxy configured to work with Dex.

    The Dex server at auth.longstorymedia.com provides:
    - OAuth2/OIDC authentication via LDAP
    - JWT tokens signed with keys available at the JWKS endpoint
    - Static clients configured including 'gmail-mcp-client'

    Returns:
        Configured OAuthProxy instance
    """
    # Get configuration from environment variables
    dex_server = os.environ.get("DEX_SERVER", "https://auth.longstorymedia.com")
    base_url = os.environ.get("MCP_SERVER_BASE_URL", "https://mcp.longstorymedia.com")
    client_id = os.environ.get("OAUTH_CLIENT_ID", "gmail-mcp-client")
    client_secret = os.environ.get("OAUTH_CLIENT_SECRET", "")
    jwt_signing_key = os.environ.get("OAUTH_JWT_SIGNING_KEY", "")

    # Configure token verification using Dex's JWKS endpoint
    token_verifier = JWTVerifier(
        jwks_uri=f"{dex_server}/keys",
        issuer=dex_server,
        audience=client_id,
    )

    # Build OAuthProxy kwargs
    auth_kwargs = {
        "upstream_authorization_endpoint": f"{dex_server}/auth",
        "upstream_token_endpoint": f"{dex_server}/token",
        "upstream_client_id": client_id,
        "token_verifier": token_verifier,
        "base_url": AnyHttpUrl(base_url),
        "allowed_client_redirect_uris": [
            "http://localhost:*",
            "http://127.0.0.1:*",
            "http://192.168.0.71:50000/mcp/auth/callback",
            "https://mcp.longstorymedia.com/mcp/auth/callback",
        ],
    }

    # Add client secret if provided
    if client_secret:
        auth_kwargs["upstream_client_secret"] = client_secret
    else:
        # For public clients without secret, we need a JWT signing key
        if jwt_signing_key:
            auth_kwargs["jwt_signing_key"] = jwt_signing_key
        else:
            # For truly public clients, set empty secret and let OAuthProxy handle it
            auth_kwargs["upstream_client_secret"] = ""

    auth = OAuthProxy(**auth_kwargs)

    return auth
