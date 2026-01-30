"""Simkl OAuth authentication with mini HTTP server."""

import http.server
import json
import logging
import socketserver
import threading
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger(__name__)


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handler for OAuth callback."""

    code: Optional[str] = None

    def do_GET(self) -> None:
        """Handle GET request from OAuth callback."""
        parsed = urlparse(self.path)

        if parsed.path == "/callback":
            query = parse_qs(parsed.query)
            if "code" in query:
                OAuthCallbackHandler.code = query["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"""
                    <html>
                    <head><title>Simkl Auth Success</title></head>
                    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                        <h1>Authentication Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                    </body>
                    </html>
                """)
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h1>Error: No code received</h1></body></html>")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging."""
        pass


class SimklOAuth:
    """Handles Simkl OAuth authentication flow."""

    AUTH_URL = "https://simkl.com/oauth/authorize"
    TOKEN_URL = "https://api.simkl.com/oauth/token"
    REDIRECT_URI = "http://localhost:8888/callback"
    PORT = 8888

    def __init__(self, client_id: str, token_file: Path):
        self.client_id = client_id
        self.token_file = token_file
        self._access_token: Optional[str] = None

    @property
    def access_token(self) -> Optional[str]:
        """Get the current access token, loading from file if needed."""
        if self._access_token:
            return self._access_token

        if self.token_file.exists():
            try:
                data = json.loads(self.token_file.read_text())
                self._access_token = data.get("access_token")
                return self._access_token
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load token file: {e}")

        return None

    def save_token(self, access_token: str) -> None:
        """Save the access token to file."""
        self._access_token = access_token
        self.token_file.write_text(json.dumps({"access_token": access_token}))
        logger.info(f"Token saved to {self.token_file}")

    def authenticate(self) -> Optional[str]:
        """
        Perform OAuth authentication flow.

        Opens browser for user to authorize, then exchanges code for token.
        """
        if self.access_token:
            logger.info("Using existing access token")
            return self.access_token

        logger.info("Starting OAuth authentication flow...")

        # Start local server
        OAuthCallbackHandler.code = None
        server = socketserver.TCPServer(("", self.PORT), OAuthCallbackHandler)
        server_thread = threading.Thread(target=server.handle_request)
        server_thread.daemon = True
        server_thread.start()

        # Open browser for authorization
        auth_url = f"{self.AUTH_URL}?response_type=code&client_id={self.client_id}&redirect_uri={self.REDIRECT_URI}"
        logger.info(f"Opening browser for authentication...")
        webbrowser.open(auth_url)

        # Wait for callback
        print("Waiting for authentication... Please authorize in your browser.")
        server_thread.join(timeout=120)  # 2 minute timeout

        server.server_close()

        if not OAuthCallbackHandler.code:
            logger.error("No authorization code received")
            return None

        # Exchange code for token
        return self._exchange_code(OAuthCallbackHandler.code)

    def _exchange_code(self, code: str) -> Optional[str]:
        """Exchange authorization code for access token."""
        try:
            response = requests.post(
                self.TOKEN_URL,
                json={
                    "code": code,
                    "client_id": self.client_id,
                    "redirect_uri": self.REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            access_token = data.get("access_token")
            if access_token:
                self.save_token(access_token)
                logger.info("Successfully obtained access token")
                return access_token
            else:
                logger.error(f"No access token in response: {data}")
                return None

        except requests.RequestException as e:
            logger.error(f"Failed to exchange code for token: {e}")
            return None
