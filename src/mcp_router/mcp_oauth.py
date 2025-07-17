"""OAuth support for MCP Server to enable Claude web integration.

This module provides OAuth 2.1 authorization code flow with PKCE for secure
authentication between Claude web and the MCP server.
"""

import secrets
import hashlib
import time
import jwt
from typing import Dict, Optional, Tuple, Any, Callable, Awaitable
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, redirect
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.backends import default_backend
import base64

from mcp_router.config import Config

# OAuth configuration
OAUTH_ISSUER = Config.OAUTH_ISSUER
OAUTH_AUDIENCE = Config.OAUTH_AUDIENCE
TOKEN_EXPIRY = Config.OAUTH_TOKEN_EXPIRY
AUTH_CODE_EXPIRY = 600  # 10 minutes

# In-memory storage for development (use Redis or DB in production)
auth_codes: Dict[str, Dict] = {}
access_tokens: Dict[str, Dict] = {}
client_registrations: Dict[str, Dict] = {}


# Generate RSA key pair for JWT signing
def generate_rsa_keypair() -> Tuple[RSAPrivateKey, RSAPublicKey]:
    """Generate RSA key pair for JWT signing

    Returns:
        Tuple of (private_key, public_key)
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    public_key = private_key.public_key()
    return private_key, public_key


# Initialize key pair
PRIVATE_KEY, PUBLIC_KEY = generate_rsa_keypair()


def get_jwks() -> Dict[str, Any]:
    """Get JSON Web Key Set for token validation

    Returns:
        Dictionary containing JWKS with public key information
    """
    # Extract modulus and exponent from public key
    public_numbers = PUBLIC_KEY.public_numbers()

    # Convert to base64url format
    def int_to_base64url(n):
        b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")

    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "mcp-router-key-1",
                "alg": "RS256",
                "n": int_to_base64url(public_numbers.n),
                "e": int_to_base64url(public_numbers.e),
            }
        ]
    }


def create_oauth_blueprint() -> Blueprint:
    """Create Flask blueprint for OAuth endpoints

    Returns:
        Flask Blueprint with OAuth endpoints configured
    """
    oauth_bp = Blueprint("oauth", __name__)

    @oauth_bp.route("/.well-known/oauth-authorization-server")
    def oauth_metadata():
        """OAuth 2.1 server metadata endpoint"""
        base_url = request.url_root.rstrip("/")
        return jsonify(
            {
                "issuer": base_url,
                "authorization_endpoint": f"{base_url}/oauth/authorize",
                "token_endpoint": f"{base_url}/oauth/token",
                "jwks_uri": f"{base_url}/.well-known/jwks.json",
                "registration_endpoint": f"{base_url}/oauth/register",
                "scopes_supported": ["mcp:read", "mcp:write", "mcp:admin"],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],  # Public clients
            }
        )

    @oauth_bp.route("/.well-known/oauth-protected-resource")
    def oauth_protected_resource():
        """OAuth 2.1 protected resource metadata endpoint"""
        base_url = request.url_root.rstrip("/")
        # Return both URLs as valid resources (with and without trailing slash)
        return jsonify(
            {
                "resource": [f"{base_url}/mcp", f"{base_url}/mcp/"],
                "authorization_servers": [base_url],
                "bearer_methods_supported": ["header"],
                "resource_signing_alg_values_supported": ["RS256"],
                "resource_documentation": f"{base_url}/docs/oauth",
                "resource_policy_uri": f"{base_url}/policy",
            }
        )

    @oauth_bp.route("/.well-known/jwks.json")
    def jwks():
        """JSON Web Key Set endpoint"""
        return jsonify(get_jwks())

    @oauth_bp.route("/oauth/register", methods=["POST"])
    def register_client():
        """Dynamic client registration (RFC 7591)"""
        data = request.json or {}

        # Generate client ID
        client_id = f"mcp-client-{secrets.token_urlsafe(16)}"

        # Store registration
        client_registrations[client_id] = {
            "client_id": client_id,
            "client_name": data.get("client_name", "MCP Client"),
            "redirect_uris": data.get("redirect_uris", []),
            "scopes": data.get("scopes", ["mcp:read"]),
            "created_at": datetime.utcnow().isoformat(),
        }

        return jsonify(
            {
                "client_id": client_id,
                "client_name": client_registrations[client_id]["client_name"],
                "redirect_uris": client_registrations[client_id]["redirect_uris"],
                "scopes": client_registrations[client_id]["scopes"],
            }
        )

    @oauth_bp.route("/oauth/authorize")
    def authorize():
        """OAuth authorization endpoint"""
        client_id = request.args.get("client_id")
        redirect_uri = request.args.get("redirect_uri")
        response_type = request.args.get("response_type")
        scope = request.args.get("scope", "mcp:read")
        state = request.args.get("state")
        code_challenge = request.args.get("code_challenge")
        code_challenge_method = request.args.get("code_challenge_method", "S256")

        # Validate request
        if response_type != "code":
            return jsonify({"error": "unsupported_response_type"}), 400

        if code_challenge_method != "S256":
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": "Only S256 code challenge method supported",
                    }
                ),
                400,
            )

        if not code_challenge:
            return (
                jsonify(
                    {
                        "error": "invalid_request",
                        "error_description": "PKCE code_challenge required",
                    }
                ),
                400,
            )

        # For simplicity, auto-approve all requests (in production, show consent screen)
        auth_code = secrets.token_urlsafe(32)

        # Store auth code with metadata
        auth_codes[auth_code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": code_challenge,
            "expires_at": time.time() + AUTH_CODE_EXPIRY,
        }

        # Redirect back to client
        redirect_url = f"{redirect_uri}?code={auth_code}"
        if state:
            redirect_url += f"&state={state}"

        return redirect(redirect_url)

    @oauth_bp.route("/oauth/token", methods=["POST"])
    def token():
        """OAuth token endpoint"""
        grant_type = request.form.get("grant_type")

        if grant_type != "authorization_code":
            return jsonify({"error": "unsupported_grant_type"}), 400

        code = request.form.get("code")
        client_id = request.form.get("client_id")
        redirect_uri = request.form.get("redirect_uri")
        code_verifier = request.form.get("code_verifier")

        # Validate auth code
        if code not in auth_codes:
            return jsonify({"error": "invalid_grant"}), 400

        auth_code_data = auth_codes[code]

        # Check expiry
        if time.time() > auth_code_data["expires_at"]:
            del auth_codes[code]
            return (
                jsonify(
                    {"error": "invalid_grant", "error_description": "Authorization code expired"}
                ),
                400,
            )

        # Validate PKCE
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        if challenge != auth_code_data["code_challenge"]:
            return (
                jsonify({"error": "invalid_grant", "error_description": "Invalid code verifier"}),
                400,
            )

        # Validate client and redirect URI
        if client_id != auth_code_data["client_id"] or redirect_uri != auth_code_data["redirect_uri"]:
            return jsonify({"error": "invalid_grant"}), 400

        # Generate access token
        now = datetime.now(timezone.utc)
        payload = {
            "iss": request.url_root.rstrip("/"),
            "aud": OAUTH_AUDIENCE,
            "sub": f"user-{secrets.token_urlsafe(8)}",  # In production, use real user ID
            "iat": now,
            "exp": now + timedelta(seconds=TOKEN_EXPIRY),
            "scope": auth_code_data["scope"],
            "client_id": client_id,
        }

        # Sign token
        access_token = jwt.encode(
            payload, PRIVATE_KEY, algorithm="RS256", headers={"kid": "mcp-router-key-1"}
        )

        # Clean up used auth code
        del auth_codes[code]

        return jsonify(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": TOKEN_EXPIRY,
                "scope": auth_code_data["scope"],
            }
        )

    return oauth_bp


def verify_token(token: str) -> Optional[Dict]:
    """Verify and decode a JWT access token"""
    try:
        # Decode and verify token
        payload = jwt.decode(token, PUBLIC_KEY, algorithms=["RS256"], audience=OAUTH_AUDIENCE)
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def create_bearer_auth_provider() -> (
    Callable[[Dict[str, str]], Awaitable[Optional[Dict[str, Any]]]]
):
    """Create a bearer token validator for FastMCP

    Returns:
        Async function that validates bearer tokens
    """

    async def validate_bearer_token(headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Validate Bearer token from request headers

        Args:
            headers: Request headers dictionary

        Returns:
            Session data dictionary if valid, None otherwise
        """
        auth_header = headers.get("authorization", "")

        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # Verify token
        payload = verify_token(token)
        if not payload:
            return None

        # Return session data
        return {
            "user_id": payload.get("sub"),
            "client_id": payload.get("client_id"),
            "scopes": payload.get("scope", "").split(),
            "token_payload": payload,
        }

    return validate_bearer_token
