#!/usr/bin/env python3
"""
Test script to simulate the complete OAuth flow and test token request.
This simulates what MCP Inspector would do.
"""

import json
import asyncio
import os
import secrets
import base64
import hashlib
import requests
from urllib.parse import parse_qs, urlparse

class OAuthFlowTester:
    def __init__(self, server_url: str | None = None):
        # Prefer env override; default to localhost to match server's Config.SERVER_URL
        self.server_url = server_url or os.environ.get("SERVER_URL", "http://localhost:8000")
        self.session = requests.Session()
        
        # Generate PKCE parameters
        self.code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
        self.code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(self.code_verifier.encode()).digest()
        ).decode().rstrip('=')
        
    def step1_register_client(self):
        """Step 1: Register OAuth client"""
        print("🔸 Step 1: Registering OAuth client...")
        
        registration_data = {
            "client_name": "OAuth Flow Test Client",
            "redirect_uris": ["http://localhost:3000/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"]
        }
        
        response = self.session.post(
            f"{self.server_url}/register",
            json=registration_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Client registration failed: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
        client_data = response.json()
        print(f"✅ Client registered successfully!")
        print(f"   Client ID: {client_data['client_id']}")
        print(f"   Client Secret: {client_data.get('client_secret', 'None (public client)')}")
        
        return client_data
    
    def step2_admin_login(self, username="admin", password="n3lNlsLkpJwCcMyoAJgO5A"):
        """Step 2: Login as admin to enable consent"""
        print("\n🔸 Step 2: Logging in as admin...")
        
        # Get login page first to initialize session
        login_page = self.session.get(f"{self.server_url}/auth/login")
        if login_page.status_code != 200:
            print(f"❌ Failed to get login page: {login_page.status_code}")
            return False
        
        # Submit login credentials
        login_response = self.session.post(
            f"{self.server_url}/auth/login",
            data={
                "username": username,
                "password": password
            },
            allow_redirects=False
        )
        
        if login_response.status_code == 302:
            print("✅ Admin login successful!")
            return True
        else:
            print(f"❌ Admin login failed: {login_response.status_code}")
            print(f"Response: {login_response.text}")
            return False
    
    def step3_authorization_request(self, client_data):
        """Step 3: Start OAuth authorization flow"""
        print("\n🔸 Step 3: Starting OAuth authorization...")
        
        # Build authorization URL
        auth_params = {
            "response_type": "code",
            "client_id": client_data["client_id"],
            "redirect_uri": "http://localhost:3000/callback",
            "scope": "mcp:read",
            "state": "test_state_123",
            "code_challenge": self.code_challenge,
            "code_challenge_method": "S256"
        }
        
        auth_response = self.session.get(
            f"{self.server_url}/authorize",
            params=auth_params,
            allow_redirects=False
        )
        
        if auth_response.status_code == 302:
            consent_url = auth_response.headers.get("Location")
            print(f"✅ Authorization request successful!")
            print(f"   Redirected to: {consent_url}")
            return consent_url
        else:
            print(f"❌ Authorization request failed: {auth_response.status_code}")
            print(f"Response: {auth_response.text}")
            return None
    
    def step4_consent_approval(self, consent_url, client_data):
        """Step 4: Approve consent and get authorization code"""
        print("\n🔸 Step 4: Handling consent approval...")
        
        # Get consent page
        consent_response = self.session.get(consent_url)
        if consent_response.status_code != 200:
            print(f"❌ Failed to get consent page: {consent_response.status_code}")
            return None
        
        # Extract CSRF state from consent page (simple extraction)
        consent_html = consent_response.text
        csrf_start = consent_html.find('name="state" value="')
        if csrf_start == -1:
            print("❌ Could not find CSRF state in consent page")
            return None
        
        csrf_start += len('name="state" value="')
        csrf_end = consent_html.find('"', csrf_start)
        csrf_state = consent_html[csrf_start:csrf_end]
        
        print(f"   Found CSRF state: {csrf_state[:20]}...")
        
        # Submit consent approval
        consent_approval = self.session.post(
            f"{self.server_url}/auth/consent",
            data={
                "action": "allow",
                "state": csrf_state
            },
            allow_redirects=False
        )
        
        if consent_approval.status_code == 302:
            callback_url = consent_approval.headers.get("Location")
            print(f"✅ Consent approved successfully!")
            print(f"   Callback URL: {callback_url}")
            
            # Extract authorization code from callback URL
            parsed_url = urlparse(callback_url)
            query_params = parse_qs(parsed_url.query)
            
            if "code" in query_params:
                auth_code = query_params["code"][0]
                print(f"   Authorization code: {auth_code[:20]}...")
                return auth_code
            else:
                print("❌ No authorization code in callback URL")
                return None
        else:
            print(f"❌ Consent approval failed: {consent_approval.status_code}")
            print(f"Response: {consent_approval.text}")
            return None
    
    def step5_token_request(self, client_data, auth_code):
        """Step 5: Exchange authorization code for access token"""
        print("\n🔸 Step 5: Exchanging code for access token...")
        
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": client_data["client_id"],
            "code_verifier": self.code_verifier
        }
        
        # Add client_secret only if it exists (confidential client)
        if client_data.get("client_secret"):
            token_data["client_secret"] = client_data["client_secret"]
        
        # Make token request
        token_response = self.session.post(
            f"{self.server_url}/token",
            data=token_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        print(f"Token response status: {token_response.status_code}")
        print(f"Token response headers: {dict(token_response.headers)}")
        print(f"Token response body: {token_response.text}")
        
        if token_response.status_code == 200:
            token_data = token_response.json()
            print("✅ Token request successful!")
            print(f"   Access Token: {token_data.get('access_token', 'N/A')[:20]}...")
            print(f"   Token Type: {token_data.get('token_type', 'N/A')}")
            print(f"   Expires In: {token_data.get('expires_in', 'N/A')} seconds")
            print(f"   Scope: {token_data.get('scope', 'N/A')}")
            return token_data
        else:
            print(f"❌ Token request failed: {token_response.status_code}")
            print(f"Response: {token_response.text}")
            return None
    
    def step6_test_mcp_access(self, token_data):
        """Step 6: Test MCP API access with token using FastMCP client (streamable-http)."""
        print("\n🔸 Step 6: Testing MCP API access with token (FastMCP client)...")

        if not token_data or "access_token" not in token_data:
            print("❌ No access token available for testing")
            return False

        async def _probe():
            from fastmcp import Client
            from fastmcp.client.auth import BearerAuth
            from fastmcp.client.logging import LogMessage
            import httpx

            # Use HTTP URL which infers Streamable HTTP transport; include Bearer token auth
            async def log_handler(message: LogMessage):
                try:
                    print(f"   [server log] {message.level or 'INFO'}: {message.data}")
                except Exception:
                    pass

            try:
                async with Client(
                    f"{self.server_url}/mcp/",
                    auth=BearerAuth(token=token_data["access_token"]),
                    log_handler=log_handler,
                    timeout=30.0,
                ) as client:
                    # Opening the client context performs the authenticated handshake to /mcp/
                    tools = await client.list_tools()
                    print(f"✅ FastMCP handshake OK, tools discovered: {len(tools)}")
                    return True
            except httpx.HTTPStatusError as e:
                resp = e.response
                print(f"❌ MCP handshake HTTP error: {resp.status_code} {resp.reason_phrase}")
                try:
                    # Show a trimmed set of headers for signal
                    hdrs = {k: v for k, v in resp.headers.items() if k.lower() in {"content-type", "x-trace-id", "server"}}
                    print(f"   Headers: {hdrs}")
                except Exception:
                    pass
                try:
                    body_text = resp.text
                    print(f"   Body: {body_text[:2000]}" )
                except Exception:
                    pass
                try:
                    body_json = resp.json()
                    print(f"   JSON: {body_json}")
                except Exception:
                    # Ignore if not JSON
                    pass
                return False
            except Exception as e:
                # Fallback for unexpected errors
                print(f"❌ MCP client unexpected error: {e}")
                if hasattr(e, "response") and getattr(e, "response") is not None:
                    try:
                        resp = e.response
                        print(f"   Status: {resp.status_code}")
                        print(f"   Body: {resp.text[:2000]}")
                    except Exception:
                        pass
                return False

        try:
            return asyncio.run(_probe())
        except Exception as e:
            print(f"❌ FastMCP client test failed: {e}")
            return False

    def step7_probe_streamable_endpoints(self, token_data):
        """Optional: Probe common streamable-http endpoints to diagnose 404s."""
        print("\n🔸 Step 7: Probing likely streamable HTTP endpoints...")

        if not token_data or "access_token" not in token_data:
            print("❌ No access token available for probing")
            return False

        candidates = [
            ("POST", f"{self.server_url}/mcp/", {}),
            ("POST", f"{self.server_url}/mcp/messages", {}),
            ("POST", f"{self.server_url}/mcp/stream", {}),
            ("GET", f"{self.server_url}/mcp/status", None),
        ]

        headers = {"Authorization": f"Bearer {token_data['access_token']}", "Content-Type": "application/json"}
        any_success = False
        for method, url, body in candidates:
            try:
                if method == "POST":
                    resp = self.session.post(url, json=body, headers=headers)
                else:
                    resp = self.session.get(url, headers=headers)
                print(f"  {method} {url} -> {resp.status_code}")
                if resp.status_code == 200:
                    any_success = True
            except Exception as e:
                print(f"  {method} {url} -> error: {e}")
        return any_success
    
    def run_complete_flow(self):
        """Run the complete OAuth flow test"""
        print("🚀 Starting Complete OAuth Flow Test")
        print("="*60)
        
        try:
            # Step 1: Register client
            client_data = self.step1_register_client()
            if not client_data:
                return False
            
            # Step 2: Admin login
            if not self.step2_admin_login():
                return False
            
            # Step 3: Authorization request
            consent_url = self.step3_authorization_request(client_data)
            if not consent_url:
                return False
            
            # Step 4: Consent approval
            auth_code = self.step4_consent_approval(consent_url, client_data)
            if not auth_code:
                return False
            
            # Step 5: Token request
            token_data = self.step5_token_request(client_data, auth_code)
            if not token_data:
                return False
            
            # Step 6: Test MCP access (JSON-RPC). Continue even if it fails to run probes.
            mcp_ok = self.step6_test_mcp_access(token_data)
            
            # Step 7: Probe streamable endpoints regardless
            self.step7_probe_streamable_endpoints(token_data)

            print("\n" + "="*60)
            if mcp_ok:
                print("🎉 COMPLETE OAUTH FLOW TEST PASSED!")
                print("✅ All steps completed successfully")
                print("✅ OAuth implementation is working correctly")
            else:
                print("⚠️ OAuth succeeded, but MCP JSON-RPC endpoint did not respond with 200.")
            return mcp_ok
            
        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    tester = OAuthFlowTester()
    success = tester.run_complete_flow()
    if success:
        # If the base JSON-RPC call worked, also probe streamable endpoints
        # to mirror MCP Inspector behavior and surface 404s clearly.
        print("\nAttempting additional streamable endpoint probes...")
        # Re-run minimal flow to get a token for probes
        client = tester.step1_register_client()
        if client and tester.step2_admin_login():
            consent = tester.step3_authorization_request(client)
            if consent:
                code = tester.step4_consent_approval(consent, client)
                if code:
                    token = tester.step5_token_request(client, code)
                    if token:
                        tester.step7_probe_streamable_endpoints(token)
    exit(0 if success else 1)