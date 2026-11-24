"""
Uploaders for YouTube Shorts and TikTok.

Both read their login details from environment variables (your .env file on
your Mac, or GitHub "Secrets" when running on the daily schedule):

  YouTube:  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
            YT_PRIVACY = public | unlisted | private   (default: private)
  TikTok:   TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
            TIKTOK_PRIVACY = SELF_ONLY | PUBLIC_TO_EVERYONE  (default: SELF_ONLY)

Run  connect_youtube.py  /  connect_tiktok.py  once to get the refresh tokens.
"""

import math
import os
import time
from pathlib import Path

import requests


def _env(name, default=""):
    return os.getenv(name, default).strip()


# =================================================================== YouTube ==
def youtube_ready():
    return all(_env(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def upload_youtube(video_path, meta):
    """Upload a Short. Returns the video URL."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=None,
        refresh_token=_env("YT_REFRESH_TOKEN"),
        client_id=_env("YT_CLIENT_ID"),
        client_secret=_env("YT_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    title = meta["title"][:95]
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"[:100]
    body = {
        "snippet": {
            "title": title,
            "description": meta.get("description", "")[:4900],
            "tags": meta.get("tags", [])[:15],
            "categoryId": _env("YT_CATEGORY", "27"),   # 27 = Education
        },
        "status": {
            "privacyStatus": _env("YT_PRIVACY", "private"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,   # AI voice - YouTube asks creators to disclose
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    return f"https://youtube.com/shorts/{response['id']}"


# ==================================================================== TikTok ==
TIKTOK_API = "https://open.tiktokapis.com/v2"


def tiktok_ready():
    return all(_env(k) for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))


def tiktok_access_token():
    r = requests.post(
        f"{TIKTOK_API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": _env("TIKTOK_CLIENT_KEY"),
            "client_secret": _env("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": _env("TIKTOK_REFRESH_TOKEN"),
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        raise RuntimeError(f"TikTok login failed: {data}")
    return data["access_token"]


def upload_tiktok(video_path, meta):
    """Post a video to TikTok. Returns the publish id."""
    token = tiktok_access_token()
    auth = {"Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8"}

    # TikTok requires checking which privacy options this account allows
    info = requests.post(f"{TIKTOK_API}/post/publish/creator_info/query/",
                         headers=auth, timeout=30).json()
    allowed = info.get("data", {}).get("privacy_level_options", ["SELF_ONLY"])
    privacy = _env("TIKTOK_PRIVACY", "SELF_ONLY")
    if privacy not in allowed:
        privacy = "SELF_ONLY" if "SELF_ONLY" in allowed else allowed[0]

    size = Path(video_path).stat().st_size
    # one chunk if under 64 MB (our Shorts are ~15-30 MB), else 10 MB chunks
    chunk = size if size <= 64 * 1024 * 1024 else 10 * 1024 * 1024
    count = 1 if chunk == size else size // chunk   # last chunk absorbs remainder

    caption = f'{meta["title"]} {" ".join("#" + t for t in meta.get("tags", [])[:5])}'
    init = requests.post(
        f"{TIKTOK_API}/post/publish/video/init/",
        headers=auth,
        json={
            "post_info": {
                "title": caption[:2200],
                "privacy_level": privacy,
                "disable_comment": False,
                "disable_duet": False,
                "disable_stitch": False,
                "is_aigc": True,           # label as AI-generated content
            },
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": chunk, "total_chunk_count": count},
        },
        timeout=30,
    ).json()
    if init.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok refused the upload: {init['error']}")
    upload_url = init["data"]["upload_url"]
    publish_id = init["data"]["publish_id"]

    with open(video_path, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            part = f.read(end - start + 1)
            r = requests.put(upload_url, data=part, timeout=300, headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            })
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"TikTok upload failed: {r.status_code} {r.text[:200]}")

    # wait (up to ~2 min) for TikTok to finish processing
    for _ in range(24):
        time.sleep(5)
        st = requests.post(f"{TIKTOK_API}/post/publish/status/fetch/", headers=auth,
                           json={"publish_id": publish_id}, timeout=30).json()
        status = st.get("data", {}).get("status", "")
        if status in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
            break
        if status == "FAILED":
            raise RuntimeError(f"TikTok processing failed: {st}")
    return f"{publish_id} ({privacy})"
