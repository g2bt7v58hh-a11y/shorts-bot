"""
One-time YouTube sign-in. Run this on your Mac:

    python connect_youtube.py

Before running: put the "client_secret....json" file you downloaded from
Google Cloud into this folder (see SETUP_PHASE2.md, step B).
A browser window opens - pick your YouTube channel's Google account and
click Allow. The keys are then saved into .env and shown for GitHub.
"""
import glob
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

HERE = Path(__file__).resolve().parent
files = glob.glob(str(HERE / "client_secret*.json"))
if not files:
    sys.exit("Couldn't find client_secret....json in this folder. See SETUP_PHASE2.md step B.")

flow = InstalledAppFlow.from_client_secrets_file(
    files[0], scopes=["https://www.googleapis.com/auth/youtube.upload"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

values = {
    "YT_CLIENT_ID": creds.client_id,
    "YT_CLIENT_SECRET": creds.client_secret,
    "YT_REFRESH_TOKEN": creds.refresh_token,
}
env = HERE / ".env"
lines = [l for l in env.read_text().splitlines() if l.split("=")[0] not in values] if env.exists() else []
lines += [f"{k}={v}" for k, v in values.items()]
env.write_text("\n".join(lines) + "\n")

print("\nYouTube connected! Saved to .env.")
print("Add these three as GitHub Secrets (SETUP_PHASE2.md step D):\n")
for k, v in values.items():
    print(f"  {k} = {v}")
