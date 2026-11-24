"""
YouTube Shorts Maker  -  Phase 1
================================
Turns a topic into a finished 1080x1920 vertical video:

    1. Gemini writes a ~45 second script, split into scenes
    2. Edge TTS reads it aloud (free) and reports when each word is spoken
    3. Pixabay (or Pexels) supplies a matching background clip for each scene
    4. Word-by-word captions are burned into the video
    5. The finished .mp4 (plus a .json with title/description/tags for
       Phase 2 uploads) is saved in the "output" folder

How to run (after setup):
    python make_short.py "the deepest place in the ocean"

Other options:
    python make_short.py "my topic" --voice en-GB-RyanNeural
    python make_short.py "my topic" --script-file my_script.txt   (use your own words, skip Gemini)
    python make_short.py --list-voices
"""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import edge_tts
import imageio_ffmpeg
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------- settings ---
HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
DEFAULT_VOICE = os.getenv("VOICE", "en-US-AndrewNeural").strip()
VOICE_SPEED = os.getenv("VOICE_SPEED", "+0%").strip()      # e.g. +0%, +10%, -5%
MUSIC_VOLUME = float(os.getenv("MUSIC_VOLUME", "0.12"))     # 0.0 - 1.0

W, H, FPS = 1080, 1920, 30
OUTPUT_DIR = HERE / "output"
CLIPS_DIR = HERE / "my_clips"      # optional: your own background videos
MUSIC_DIR = HERE / "music"         # optional: background music (.mp3)
FONTS_DIR = HERE / "fonts"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
PROXY = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")  # only used if set


def log(msg):
    print(f"  {msg}", flush=True)


# ------------------------------------------------------------ 1. the script ---
SCRIPT_PROMPT = """You write viral YouTube Shorts scripts.

Topic: "{topic}"

Write a voiceover script that takes about 45 seconds to read aloud
(about 140 words total - between 130 and 145). Rules:
- Open with a scroll-stopping hook in the first sentence (a surprising fact,
  bold claim or question). No "Hey guys", no "In this video".
- Short, punchy sentences. Conversational. One idea per sentence.
- Build curiosity, deliver 3-4 genuinely interesting facts, end with a
  memorable line or a question that invites comments.
- Plain spoken text only: no emojis, hashtags, stage directions or markdown.
- Only state facts you are confident are true. Do not exaggerate for drama.

Split the script into 6-9 scenes. For each scene give a 1-3 word stock-footage
search query describing something that can be FILMED (e.g. "ocean waves",
"city night", "scientist lab") - concrete visuals, not abstract ideas.

Reply with JSON only, in exactly this shape:
{{
  "title": "catchy YouTube title under 70 characters",
  "scenes": [{{"narration": "...", "search": "..."}}],
  "description": "2-3 sentence YouTube description",
  "hashtags": ["#shorts", "..."]
}}"""


def write_script_with_gemini(topic):
    if not GEMINI_API_KEY:
        sys.exit(
            "\nERROR: No Gemini key found.\n"
            "Open the .env file in this folder and paste your key after GEMINI_API_KEY=\n"
            "(or use --script-file to supply your own script).\n"
        )
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    backups = ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash",
               "gemini-3.5-flash", "gemini-3.5-flash-lite")
    models = [GEMINI_MODEL] + [m for m in backups if m != GEMINI_MODEL]
    last_err, best = None, None
    MIN_WORDS = 120   # ~42 seconds of speech
    # Google sometimes says "busy" - try each model, and wait and retry a few rounds
    attempts = [(rnd, m) for rnd in range(4) for m in models]
    for n, (rnd, model) in enumerate(attempts):
        if rnd and model == models[0]:
            wait = 10 * rnd
            log(f"Gemini is busy - waiting {wait}s and trying again...")
            import time; time.sleep(wait)
        try:
            resp = client.models.generate_content(
                model=model,
                contents=SCRIPT_PROMPT.format(topic=topic),
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=0.9
                ),
            )
            data = json.loads(resp.text)
            if not data.get("scenes"):
                raise ValueError("Gemini returned no scenes")
            words = sum(len(s.get("narration", "").split()) for s in data["scenes"])
            if best is None or words > best[0]:
                best = (words, data)
            if words >= MIN_WORDS:
                return data
            log(f"script too short ({words} words, want ~140) - asking again...")
        except Exception as e:  # try the next model name
            last_err = e
            log(f"(model {model} failed: {str(e)[:120]})")
    if best:
        return best[1]   # use the longest script we got
    sys.exit(f"\nERROR: Gemini could not write the script: {last_err}\n")


def script_from_file(path, topic):
    """Use your own text. Each sentence becomes a scene; visuals search the topic."""
    text = Path(path).read_text(encoding="utf-8").strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    # merge into ~6-9 scenes
    n = max(1, round(len(sentences) / 8))
    scenes = [
        {"narration": " ".join(sentences[i:i + n]), "search": topic}
        for i in range(0, len(sentences), n)
    ]
    return {
        "title": topic.title()[:70],
        "scenes": scenes,
        "description": text[:200],
        "hashtags": ["#shorts"],
    }


# ------------------------------------------------------------- 2. the voice ---
async def _tts(text, voice, mp3_path):
    comm = edge_tts.Communicate(
        text, voice, rate=VOICE_SPEED, boundary="WordBoundary", proxy=PROXY
    )
    words = []
    with open(mp3_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000          # 100ns units -> seconds
                words.append({
                    "word": chunk["text"],
                    "start": start,
                    "end": start + chunk["duration"] / 10_000_000,
                })
    return words


def make_voiceover(text, voice, mp3_path):
    words = asyncio.run(_tts(text, voice, mp3_path))
    if not words:
        sys.exit("ERROR: The voice service returned no audio. Check your internet connection.")
    return words


def media_duration(path):
    """Ask ffmpeg how long a media file is (seconds)."""
    out = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


# ----------------------------------------------------------- 3. the visuals ---
def pexels_find_video(query, used_ids, min_seconds):
    """Return a download URL for a portrait clip matching the query, or None."""
    if not PEXELS_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "orientation": "portrait", "per_page": 15},
            timeout=30,
        )
        if r.status_code == 401:
            log("Pexels rejected the API key - check PEXELS_API_KEY in .env")
            return None
        r.raise_for_status()
    except requests.RequestException as e:
        log(f"Pexels search failed for '{query}': {e}")
        return None

    videos = [v for v in r.json().get("videos", []) if v["id"] not in used_ids]
    # prefer clips long enough to cover the scene, then randomise a little
    videos.sort(key=lambda v: (v.get("duration", 0) < min_seconds, random.random()))
    for v in videos:
        files = [
            f for f in v.get("video_files", [])
            if f.get("height") and f.get("width") and f["height"] > f["width"]
            and f["height"] >= 1280 and f.get("link")
        ]
        if not files:
            continue
        best = min(files, key=lambda f: abs(f["height"] - 1920))  # closest to 1080x1920
        used_ids.add(v["id"])
        return best["link"]
    return None


def pixabay_find_video(query, used_ids, min_seconds):
    """Return a download URL for a Pixabay clip matching the query, or None."""
    if not PIXABAY_API_KEY:
        return None
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": PIXABAY_API_KEY, "q": query[:100], "per_page": 20,
                    "safesearch": "true", "order": "popular"},
            timeout=30,
        )
        if r.status_code in (400, 401, 403) and "key" in r.text.lower():
            log("Pixabay rejected the API key - check PIXABAY_API_KEY in .env")
            return None
        r.raise_for_status()
    except requests.RequestException as e:
        log(f"Pixabay search failed for '{query}': {e}")
        return None

    def pick(hit):
        # largest version up to 4K that has a real link
        files = [f for f in hit.get("videos", {}).values()
                 if f.get("url") and f.get("height", 0) >= 720 and f.get("width", 0) <= 3840]
        return max(files, key=lambda f: f["height"]) if files else None

    hits = [h for h in r.json().get("hits", []) if h["id"] not in used_ids and pick(h)]
    # prefer: vertical clips, then long-enough clips, then a little randomness
    hits.sort(key=lambda h: (pick(h)["height"] <= pick(h)["width"],
                             h.get("duration", 0) < min_seconds, random.random()))
    if not hits:
        return None
    used_ids.add(hits[0]["id"])
    return pick(hits[0])["url"]


def find_video(query, used_ids, min_seconds):
    """Try each stock-video site you have a key for, with a simpler query as backup."""
    simpler = query.split()[-1] if " " in query else None
    for q in filter(None, [query, simpler]):
        for site, finder in (("Pixabay", pixabay_find_video), ("Pexels", pexels_find_video)):
            url = finder(q, used_ids, min_seconds)
            if url:
                return site, q, url
    return None, None, None


def download(url, dest):
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for part in r.iter_content(1 << 20):
                f.write(part)
    return dest


def own_clips():
    exts = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".jpg", ".jpeg", ".png"}
    return sorted(p for p in CLIPS_DIR.glob("*") if p.suffix.lower() in exts)


def make_segment(source, seconds, out_path, index):
    """Turn any clip/image (or nothing) into an exact-length 1080x1920 segment."""
    fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
           f"setsar=1,fps={FPS}")
    if source is None:
        # colourful animated fallback background
        palettes = [("0x1e3c72", "0x2a5298"), ("0x42275a", "0x734b6d"),
                    ("0x0f2027", "0x2c5364"), ("0x614385", "0x516395"),
                    ("0x134e5e", "0x71b280"), ("0x833ab4", "0xfd1d1d")]
        c0, c1 = palettes[index % len(palettes)]
        inputs = ["-f", "lavfi", "-i",
                  f"gradients=s={W}x{H}:c0={c0}:c1={c1}:x0=0:y0=0:x1={W}:y1={H}:speed=0.02:r={FPS}"]
        vf = "setsar=1"
    elif Path(source).suffix.lower() in {".jpg", ".jpeg", ".png"}:
        # still image: slow zoom ("Ken Burns") effect
        frames = int(seconds * FPS) + 1
        inputs = ["-loop", "1", "-i", str(source)]
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='min(zoom+0.0008,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':"
              f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1")
    else:
        inputs = ["-stream_loop", "-1", "-i", str(source)]   # loop if clip is too short
        vf = fit
    cmd = [FFMPEG, "-y", "-loglevel", "error", *inputs, "-t", f"{seconds:.3f}",
           "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", str(out_path)]
    subprocess.run(cmd, check=True)


def build_visuals(scenes, timings, work):
    used, clips, segments = set(), own_clips(), []
    if not (PIXABAY_API_KEY or PEXELS_API_KEY) and not clips:
        log("No Pixabay/Pexels key and no clips in my_clips/ -> using coloured backgrounds")
    for i, (scene, (t0, t1)) in enumerate(zip(scenes, timings)):
        seconds = t1 - t0
        source = None
        site, q, url = find_video(scene["search"], used, seconds)
        if url:
            log(f"scene {i+1}: '{q}' -> {site} clip")
            try:
                source = download(url, work / f"raw_{i}.mp4")
            except requests.RequestException as e:
                log(f"  download failed ({e}); using a backup background")
        elif clips:
            source = clips[i % len(clips)]
            log(f"scene {i+1}: using your clip {source.name}")
        else:
            log(f"scene {i+1}: '{scene['search']}' -> coloured background")
        seg = work / f"seg_{i:02d}.mp4"
        make_segment(source, seconds, seg, i)
        segments.append(seg)
    return segments


def scene_timings(scenes, words, total):
    """Work out when each scene starts/ends by matching its words to the voice timings."""
    counts = [len(re.findall(r"[\w']+", s["narration"])) for s in scenes]
    timings, idx, start = [], 0, 0.0
    for n, scene in enumerate(scenes):
        idx = min(idx + counts[n], len(words))
        if n == len(scenes) - 1 or idx >= len(words):
            end = total
        else:
            end = words[idx]["start"]   # next scene starts when its first word is spoken
        timings.append((start, max(end, start + 0.5)))
        start = end
        if end >= total:
            break
    return timings


# ---------------------------------------------------------- 4. the captions ---
def ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def write_captions(words, total, path, script_text=""):
    """Big bold word-by-word captions; the word being spoken is highlighted yellow."""
    header = textwrap.dedent(f"""\
        [Script Info]
        ScriptType: v4.00+
        PlayResX: {W}
        PlayResY: {H}
        WrapStyle: 0

        [V4+ Styles]
        Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
        Style: Cap,Inter Black,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,4,5,80,80,0,1

        [Events]
        Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        """)

    # The voice timings drop punctuation, so line each spoken word up with the
    # original script to find where sentences/phrases end.
    def norm(s):
        return re.sub(r"[^\w]", "", s.lower())
    tokens = script_text.split()
    ti = 0
    for w in words:
        target = norm(w["word"])
        w["pause_after"] = False
        for look in range(ti, min(ti + 4, len(tokens))):   # small look-ahead
            if target and (norm(tokens[look]).startswith(target) or target.startswith(norm(tokens[look]) or "#")):
                ti = look
                # only mark a break if this spoken word finishes the token
                if norm(tokens[look]).endswith(target):
                    w["pause_after"] = bool(re.search(r"[.,!?;:—-]$", tokens[look]))
                    ti = look + 1
                break

    # group words into short chunks (max 3 words, break after punctuation)
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or w["pause_after"]:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)

    lines = []
    for ci, chunk in enumerate(chunks):
        chunk_end = chunks[ci + 1][0]["start"] if ci + 1 < len(chunks) else total
        for wi, w in enumerate(chunk):
            start = w["start"]
            end = chunk[wi + 1]["start"] if wi + 1 < len(chunk) else chunk_end
            parts = []
            for wj, other in enumerate(chunk):
                txt = other["word"].upper().replace("{", "").replace("}", "")
                if wj == wi:
                    parts.append(r"{\c&H00E5FF&\fscx112\fscy112}" + txt + r"{\r}")
                else:
                    parts.append(txt)
            # \pos puts captions a bit below the centre of the screen
            lines.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,"
                f"{{\\pos({W//2},{int(H*0.62)})}}" + " ".join(parts)
            )
    Path(path).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------- 5. final assembly ---
def assemble(segments, voice_mp3, captions, total, out_path, work):
    concat = work / "list.txt"
    concat.write_text("".join(f"file '{s.name}'\n" for s in segments))
    music = sorted(MUSIC_DIR.glob("*.mp3"))
    fonts_rel = os.path.relpath(FONTS_DIR, work).replace("\\", "/")

    cmd = [FFMPEG, "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", concat.name,
           "-i", voice_mp3.name]
    if music:
        track = random.choice(music)
        log(f"adding background music: {track.name}")
        cmd += ["-stream_loop", "-1", "-i", str(track)]
        audio = (f"[2:a]volume={MUSIC_VOLUME}[m];"
                 f"[1:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]")
    else:
        audio = "[1:a]anull[a]"
    filters = f"[0:v]subtitles={captions.name}:fontsdir={fonts_rel}[v];{audio}"
    cmd += ["-filter_complex", filters, "-map", "[v]", "-map", "[a]",
            "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(out_path.resolve())]
    # run inside the work folder so file paths stay simple on Windows too
    subprocess.run(cmd, check=True, cwd=work)


# -------------------------------------------------------------------- main ---
def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "short"


def make_video(topic, voice=DEFAULT_VOICE, script_file=None, keep_temp=False):
    """Make one Short. Returns (path_to_mp4, details_dict)."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}_{slugify(topic)}"
    work = OUTPUT_DIR / f"_work_{name}"
    work.mkdir(parents=True, exist_ok=True)

    print(f"\n[1/5] Writing the script about: {topic}")
    data = (script_from_file(script_file, topic) if script_file
            else write_script_with_gemini(topic))
    scenes = [s for s in data["scenes"] if s.get("narration", "").strip()]
    full_text = " ".join(s["narration"].strip() for s in scenes)
    log(f'title: {data["title"]}  ({len(full_text.split())} words)')

    print(f"[2/5] Recording the voiceover ({voice})")
    voice_mp3 = work / "voice.mp3"
    words = make_voiceover(full_text, voice, voice_mp3)
    total = media_duration(voice_mp3) + 0.4
    log(f"length: {total:.1f} seconds")

    print("[3/5] Getting background visuals")
    timings = scene_timings(scenes, words, total)
    segments = build_visuals(scenes[:len(timings)], timings, work)

    print("[4/5] Creating captions")
    captions = work / "captions.ass"
    write_captions(words, total, captions, full_text)

    print("[5/5] Putting the video together (this can take a minute)")
    out_mp4 = OUTPUT_DIR / f"{name}.mp4"
    assemble(segments, voice_mp3, captions, total, out_mp4, work)

    # details for Phase 2 (YouTube upload)
    meta = {
        "topic": topic,
        "title": data["title"],
        "description": data.get("description", "") + "\n\n" + " ".join(data.get("hashtags", [])),
        "tags": [h.lstrip("#") for h in data.get("hashtags", [])],
        "script": full_text,
        "scenes": scenes,
        "video_file": out_mp4.name,
        "duration_seconds": round(total, 1),
        "created": stamp,
        "uploaded": False,
    }
    (OUTPUT_DIR / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    if not keep_temp:
        shutil.rmtree(work, ignore_errors=True)
    return out_mp4, meta


def main():
    p = argparse.ArgumentParser(description="Make a YouTube Short from a topic.")
    p.add_argument("topic", nargs="?", help='e.g. "why octopuses have three hearts"')
    p.add_argument("--voice", default=DEFAULT_VOICE, help="Edge TTS voice name")
    p.add_argument("--script-file", help="use your own script text instead of Gemini")
    p.add_argument("--keep-temp", action="store_true", help="keep working files")
    p.add_argument("--list-voices", action="store_true", help="show English voices")
    args = p.parse_args()

    if args.list_voices:
        voices = asyncio.run(edge_tts.list_voices(proxy=PROXY))
        for v in voices:
            if v["Locale"].startswith("en-"):
                print(f'{v["ShortName"]:32} {v["Gender"]}')
        return
    if not args.topic:
        args.topic = input("What should the Short be about? ").strip()
        if not args.topic:
            sys.exit("No topic given.")

    out_mp4, _ = make_video(args.topic, args.voice, args.script_file, args.keep_temp)
    print(f"\nDone! Your Short is ready:\n  {out_mp4}\n")

if __name__ == "__main__":
    main()
