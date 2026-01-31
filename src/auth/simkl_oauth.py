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

    def __init__(self, client_id: str, client_secret: str, token_file: Path, port: int = 19877):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_file = token_file
        self.PORT = port
        self.REDIRECT_URI = f"http://localhost:{port}/callback"
        self._access_token: Optional[str] = None
        self._last_error: Optional[str] = None

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

    def get_auth_url(self) -> str:
        """Get the authorization URL without opening browser."""
        return f"{self.AUTH_URL}?response_type=code&client_id={self.client_id}&redirect_uri={self.REDIRECT_URI}"

    def start_callback_server(self) -> None:
        """Start the OAuth callback server in a background thread."""
        OAuthCallbackHandler.code = None
        self._server = socketserver.TCPServer(("", self.PORT), OAuthCallbackHandler)
        self._server_thread = threading.Thread(target=self._server.handle_request)
        self._server_thread.daemon = True
        self._server_thread.start()
        logger.info(f"OAuth callback server started on port {self.PORT}")

    def wait_for_callback(self, timeout: int = 300) -> Optional[str]:
        """Wait for OAuth callback and exchange code for token."""
        self._server_thread.join(timeout=timeout)
        self._server.server_close()
        if not OAuthCallbackHandler.code:
            self._last_error = "Aucun code reçu — autorisation annulée ou délai dépassé (5 min)"
            logger.error("No authorization code received (timeout or cancelled)")
            return None
        token = self._exchange_code(OAuthCallbackHandler.code)
        if not token and not self._last_error:
            self._last_error = "Échange du code échoué — voir les logs du serveur"
        return token

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
                    "client_secret": self.client_secret,
                    "redirect_uri": self.REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                timeout=30,
            )
            data = response.json()

            if not response.ok:
                self._last_error = f"Simkl a rejeté la requête: {data.get('message', data)}"
                logger.error(f"Token exchange failed ({response.status_code}): {data}")
                return None

            access_token = data.get("access_token")
            if access_token:
                self.save_token(access_token)
                logger.info("Successfully obtained access token")
                return access_token
            else:
                self._last_error = f"Pas de token dans la réponse: {data}"
                logger.error(f"No access token in response: {data}")
                return None

        except requests.RequestException as e:
            self._last_error = f"Erreur réseau lors de l'échange: {e}"
            logger.error(f"Failed to exchange code for token: {e}")
            return None
