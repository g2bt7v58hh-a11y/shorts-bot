"""
Automatic poster: picks a fresh topic in your niche, makes the Short, and
uploads it to YouTube and TikTok. Runs once per call; GitHub Actions calls it
on a daily schedule (see .github/workflows/daily-short.yml).

    python auto_post.py                 # normal run
    python auto_post.py --no-upload     # make the video only (for testing)
    python auto_post.py --topic "..."   # use a specific topic

Settings (in .env or GitHub Secrets/Variables):
    NICHE = the theme of your channel, e.g. "mind-blowing ocean and nature facts"
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import make_short as ms
import uploaders

# each channel keeps its own list (channel 2 uses HISTORY_FILE=history2.json)
HISTORY = ms.HERE / os.getenv("HISTORY_FILE", "history.json")
# Several niches separated by commas or "|" -> the bot takes turns between them.
NICHES = [n.strip() for n in os.getenv("NICHE", "").replace("|", ",").split(",") if n.strip()] \
    or ["weird history", "reddit stories"]
STORY_VOICE = os.getenv("STORY_VOICE", "en-US-AvaNeural").strip()


def load_history():
    return json.loads(HISTORY.read_text()) if HISTORY.exists() else []


def pick_topic(history, niche):
    """Ask Gemini for a fresh, specific topic in the niche that we haven't done."""
    from google import genai
    from google.genai import types

    done = [h["topic"] for h in history][-150:]
    if ms.is_story(niche):
        ask = ("Suggest ONE new, original story premise (one sentence, e.g. 'refusing to pay "
               "for my brother-in-law's surprise vacation'). Make it relatable, dramatic and "
               "different from the ones above.")
    else:
        ask = ("Suggest ONE new, specific topic with a strong curiosity hook that fits the "
               "niche, is factually solid, and would make viewers stop scrolling.")
    prompt = f"""You choose topics for a YouTube Shorts / TikTok channel.
Channel niche: "{niche}"

Already covered (do NOT repeat or closely overlap these):
{json.dumps(done, indent=0) if done else "(nothing yet)"}

{ask}
Reply with JSON only: {{"topic": "..."}}"""

    client = genai.Client(api_key=ms.GEMINI_API_KEY)
    models = [ms.GEMINI_MODEL, "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash",
              "gemini-3.5-flash-lite"]
    for attempt in range(4):
        for model in models:
            try:
                r = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", temperature=1.0))
                topic = json.loads(r.text)["topic"].strip()
                if topic and topic.lower() not in (d.lower() for d in done):
                    return topic
            except Exception as e:
                ms.log(f"(topic picker: {model} failed: {str(e)[:100]})")
        time.sleep(15 * (attempt + 1))
    sys.exit("Could not get a topic from Gemini.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--topic")
    p.add_argument("--no-upload", action="store_true")
    args = p.parse_args()

    history = load_history()
    niche = NICHES[len(history) % len(NICHES)]          # take turns between niches
    topic = args.topic or pick_topic(history, niche)
    print(f"Niche: {niche}\nToday's topic: {topic}")

    story = ms.is_story(niche)
    voice = STORY_VOICE if story else ms.DEFAULT_VOICE
    video, meta = ms.make_video(topic, voice=voice, style="story" if story else "facts")
    entry = {"niche": niche, "topic": topic, "title": meta["title"], "video_file": video.name,
             "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    failures = []
    if not args.no_upload:
        for name, ready, upload in (("youtube", uploaders.youtube_ready, uploaders.upload_youtube),
                                    ("tiktok", uploaders.tiktok_ready, uploaders.upload_tiktok)):
            if not ready():
                print(f"[{name}] not connected yet - skipping")
                continue
            try:
                print(f"[{name}] uploading...")
                entry[name] = upload(video, meta)
                print(f"[{name}] done: {entry[name]}")
            except Exception as e:
                failures.append(name)
                entry[name] = f"FAILED: {e}"
                print(f"[{name}] FAILED: {e}")

    history.append(entry)
    HISTORY.write_text(json.dumps(history, indent=2))
    print("\nSummary:", json.dumps(entry, indent=2))
    if failures:
        sys.exit(f"Upload failed for: {', '.join(failures)}")   # makes GitHub email you


if __name__ == "__main__":
    main()
