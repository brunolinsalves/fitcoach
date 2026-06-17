#!/usr/bin/env python3
"""
fetch_strava.py

Strava API data collection script.
Handles OAuth2 authentication (first-time browser flow + automatic token refresh)
and downloads recent activities for training load calculation.
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import date, timedelta, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"
REDIRECT_PORT = 5000
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
TOKEN_FILE = "strava_tokens.json"


# ---------------------------------------------------------------------------
# OAuth2 helpers
# ---------------------------------------------------------------------------

class _CallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler to capture the OAuth2 redirect code."""
    authorization_code = None

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = qs.get("code", [None])[0]
        if code:
            _CallbackHandler.authorization_code = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>&#10004; Autorizado com sucesso!</h2>"
                b"<p>Pode fechar esta aba e voltar ao terminal.</p></body></html>"
            )
        else:
            error = qs.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Erro: {error}</h2></body></html>".encode())

    def log_message(self, fmt, *args):
        pass  # suppress noisy logs


def _get_credentials():
    client_id = os.getenv("STRAVA_CLIENT_ID")
    client_secret = os.getenv("STRAVA_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "Error: STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env.\n"
            "Create your Strava app at https://www.strava.com/settings/api",
            file=sys.stderr,
        )
        sys.exit(1)
    return client_id, client_secret


def _save_tokens(tokens: dict, path: str):
    with open(path, "w") as f:
        json.dump(tokens, f, indent=2)


def _load_tokens(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def authorize_first_time(client_id: str, client_secret: str, token_path: str) -> dict:
    """Run the full OAuth2 authorization code flow with a local callback server."""
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "approval_prompt": "force",
        "scope": "read_all,activity:read_all",
    }
    auth_url = f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    print(f"\nOpening browser for Strava authorization...")
    print(f"If the browser doesn't open, visit:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # Start local server to capture redirect
    server = HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server.timeout = 120  # 2 min timeout
    print(f"Waiting for authorization callback on port {REDIRECT_PORT}...")
    server.handle_request()

    code = _CallbackHandler.authorization_code
    if not code:
        print("Error: No authorization code received.", file=sys.stderr)
        sys.exit(1)

    # Exchange code for tokens
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()
    _save_tokens(tokens, token_path)
    print(f"Strava tokens saved to {token_path}")
    return tokens


def refresh_tokens(client_id: str, client_secret: str, tokens: dict, token_path: str) -> dict:
    """Refresh the access token using the stored refresh_token."""
    resp = requests.post(STRAVA_TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": tokens["refresh_token"],
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    new_tokens = resp.json()
    # Preserve athlete info from original tokens
    if "athlete" not in new_tokens and "athlete" in tokens:
        new_tokens["athlete"] = tokens["athlete"]
    _save_tokens(new_tokens, token_path)
    return new_tokens


def get_access_token(token_path: str = TOKEN_FILE) -> str:
    """Get a valid access token, refreshing or authorizing as needed."""
    client_id, client_secret = _get_credentials()
    tokens = _load_tokens(token_path)

    if not tokens:
        tokens = authorize_first_time(client_id, client_secret, token_path)
    elif tokens.get("expires_at", 0) < time.time():
        print("Strava token expired, refreshing...")
        tokens = refresh_tokens(client_id, client_secret, tokens, token_path)
    else:
        print("Using cached Strava token.")

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Activity fetching
# ---------------------------------------------------------------------------

def fetch_activities(access_token: str, days: int = 42) -> list[dict]:
    """Fetch athlete activities from the last N days."""
    after_epoch = int((datetime.now() - timedelta(days=days)).timestamp())
    all_activities = []
    page = 1
    per_page = 100

    while True:
        resp = requests.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": after_epoch, "per_page": per_page, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_activities.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    return all_activities


def simplify_activity(act: dict) -> dict:
    """Extract the fields we need from a Strava SummaryActivity."""
    return {
        "id": act.get("id"),
        "name": act.get("name"),
        "sport_type": act.get("sport_type") or act.get("type"),
        "type": act.get("type"),
        "start_date": act.get("start_date"),
        "start_date_local": act.get("start_date_local"),
        "moving_time_seconds": act.get("moving_time"),
        "elapsed_time_seconds": act.get("elapsed_time"),
        "distance_meters": act.get("distance"),
        "has_heartrate": act.get("has_heartrate", False),
        "average_heartrate": act.get("average_heartrate"),
        "max_heartrate": act.get("max_heartrate"),
        "average_watts": act.get("average_watts"),
        "weighted_average_watts": act.get("weighted_average_watts"),
        "kilojoules": act.get("kilojoules"),
        "source": "strava",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_arguments():
    parser = argparse.ArgumentParser(description="Fetch activities from Strava API.")
    parser.add_argument("--days", type=int, default=42, help="Number of days to look back (default: 42)")
    parser.add_argument("--output", type=str, default="strava_activities.json", help="Output JSON file")
    return parser.parse_args()


def main():
    args = parse_arguments()
    token_path = TOKEN_FILE

    print(f"Fetching Strava activities for the last {args.days} days...")
    access_token = get_access_token(token_path)
    raw_activities = fetch_activities(access_token, days=args.days)

    simplified = [simplify_activity(a) for a in raw_activities]

    # Summary
    types = {}
    for a in simplified:
        t = a["sport_type"] or "Unknown"
        types[t] = types.get(t, 0) + 1

    print(f"  Found {len(simplified)} activities:")
    for t, count in sorted(types.items()):
        print(f"    {t}: {count}")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(simplified, f, indent=2, ensure_ascii=False)
    print(f"  Saved to {args.output}")


if __name__ == "__main__":
    main()
