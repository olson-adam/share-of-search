"""Minimal stdlib OAuth for the Google APIs the capture/yield layers read.

Deliberately separate from gcloud ADC: the keyword-planner provider rides the
user's existing ADC refresh token, and re-consenting ADC with extra scopes
would risk breaking that bridge. This helper runs its own installed-app flow
(reusing the public client id/secret already present in the ADC file), asks
only for read scopes, and stores its token where the workspace owner can see
and delete it.

    from google_auth import access_token
    token = access_token()   # opens a browser ONCE, then refreshes silently

Scopes: Search Console read + Analytics read.
"""
from __future__ import annotations

import http.server
import json
import os
import secrets
import sys
import urllib.error
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly",
          "https://www.googleapis.com/auth/analytics.readonly"]
TOKEN_PATH = Path.home() / ".config" / "share-of-search" / "google-token.json"
ADC_PATH = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
REDIRECT_PORT = 8123


def _client() -> tuple[str, str]:
    if not ADC_PATH.exists():
        raise SystemExit("error: no gcloud ADC found — run `gcloud auth application-default "
                         "login` once (any account) so an OAuth client id is available")
    adc = json.loads(ADC_PATH.read_text())
    return adc["client_id"], adc["client_secret"]


def _token_request(data: dict) -> dict:
    req = urllib.request.Request("https://oauth2.googleapis.com/token",
                                 data=urllib.parse.urlencode(data).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _consent_flow(client_id: str, client_secret: str) -> dict:
    state = secrets.token_urlsafe(16)
    code_holder: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state and "code" in q:
                code_holder["code"] = q["code"][0]
                body = b"<h3>share-of-search: connected. You can close this tab.</h3>"
            else:
                body = b"<h3>share-of-search: authorization failed.</h3>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    redirect = f"http://localhost:{REDIRECT_PORT}"
    url = ("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "state": state}))
    print("opening browser for a one-time consent (Search Console + Analytics, read-only)…",
          file=sys.stderr)
    webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()
    if "code" not in code_holder:
        raise SystemExit("error: authorization timed out or was denied")
    tok = _token_request({"code": code_holder["code"], "client_id": client_id,
                          "client_secret": client_secret, "redirect_uri": redirect,
                          "grant_type": "authorization_code"})
    if "refresh_token" not in tok:
        raise SystemExit("error: no refresh_token in response — remove the app at "
                         "myaccount.google.com/permissions and retry")
    return tok


def access_token() -> str:
    client_id, client_secret = _client()
    stored = json.loads(TOKEN_PATH.read_text()) if TOKEN_PATH.exists() else {}
    if stored.get("refresh_token"):
        try:
            tok = _token_request({"refresh_token": stored["refresh_token"],
                                  "client_id": client_id, "client_secret": client_secret,
                                  "grant_type": "refresh_token"})
            if "access_token" in tok:
                return tok["access_token"]
        except urllib.error.HTTPError:
            pass  # revoked/expired token answers 400 (RFC 6749 §5.2) — re-consent
        print("stored token no longer valid — re-consenting…", file=sys.stderr)
    tok = _consent_flow(client_id, client_secret)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(TOKEN_PATH.parent, 0o700)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"refresh_token": tok["refresh_token"]}, indent=2))
    print(f"token stored → {TOKEN_PATH}", file=sys.stderr)
    return tok["access_token"]


def api_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def api_post(url: str, token: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())
