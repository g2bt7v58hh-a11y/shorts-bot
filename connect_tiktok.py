"""
One-time TikTok sign-in. Run this on your Mac:

    python connect_tiktok.py

Before running, add these to .env (from your TikTok developer app):
    TIKTOK_CLIENT_KEY=...
    TIKTOK_CLIENT_SECRET=...
    TIKTOK_REDIRECT_URI=...   (exactly as entered in the TikTok app settings)
"""
import os
import secrets
import sys
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
key = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
secret = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
redirect = os.getenv("TIKTOK_REDIRECT_URI", "").strip()
if not (key and secret and redirect):
    sys.exit("Add TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET and TIKTOK_REDIRECT_URI to .env first.")

state = secrets.token_urlsafe(16)
url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
    "client_key": key, "response_type": "code", "redirect_uri": redirect,
    "scope": "user.info.basic,video.publish,video.upload", "state": state,
})
print("\n1. Open this link, log in to TikTok and click Authorize:\n")
print("   " + url + "\n")
print("2. You'll land on another page (it may look blank or show an error - that's fine).")
print("   Copy the FULL address from the browser's address bar and paste it here.\n")
back = input("Paste the address: ").strip()
q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
if "code" not in q:
    sys.exit(f"No code found in that address: {q.get('error_description', q)}")

r = requests.post("https://open.tiktokapis.com/v2/oauth/token/",
                  headers={"Content-Type": "application/x-www-form-urlencoded"},
                  data={"client_key": key, "client_secret": secret, "code": q["code"][0],
                        "grant_type": "authorization_code", "redirect_uri": redirect},
                  timeout=30).json()
if "refresh_token" not in r:
    sys.exit(f"TikTok said: {r}")

env = HERE / ".env"
lines = [l for l in env.read_text().splitlines() if not l.startswith("TIKTOK_REFRESH_TOKEN=")]
lines.append(f"TIKTOK_REFRESH_TOKEN={r['refresh_token']}")
env.write_text("\n".join(lines) + "\n")
print("\nTikTok connected! Saved to .env.")
print("Add this as a GitHub Secret too (SETUP_PHASE2.md step D):\n")
print(f"  TIKTOK_REFRESH_TOKEN = {r['refresh_token']}")
print("\n(This sign-in lasts about a year - just run this again when it expires.)")
