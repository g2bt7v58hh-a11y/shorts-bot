# Shorts Bot: Phase 1

Type a topic and get a finished 1080x1920 YouTube Short, with an AI script, voiceover, background video and word-by-word captions.

## One-time setup

**Windows**
1. Double-click `setup_windows.bat`.
   - If Python isn't installed, the script opens the download page. Install Python and **tick "Add python.exe to PATH"** on the first screen, then double-click `setup_windows.bat` again.
2. Notepad opens a file called `.env`. Paste your two keys after the `=` signs, then save:
   ```
   GEMINI_API_KEY=your-gemini-key
   PIXABAY_API_KEY=your-pixabay-key
   ```

**Mac**
1. Right-click `setup_mac.command`, choose **Open**, then click **Open** again. You only need to right-click the first time.
2. TextEdit opens `.env`. Paste your keys the same way, then save.

## Making a video

- **Windows:** double-click `make_video_windows.bat`
- **Mac:** double-click `make_video_mac.command`

Type a topic and press Enter. About a minute later the `output` folder opens with:
- `....mp4`: your Short
- `....json`: its title, description and hashtags, which Phase 2 uses to upload it

## Optional extras
| Want to... | Do this |
|---|---|
| Add background music | Put `.mp3` files in the `music` folder. One is picked at random and played quietly. |
| Use your own footage | Put videos or images in `my_clips`. They're used when Pixabay has nothing, or if you have no Pixabay key. |
| Change the voice | Run `python make_short.py --list-voices`, then set `VOICE=` in `.env` |
| Speak faster or slower | Change `VOICE_SPEED=` in `.env` (e.g. `+10%` or `-5%`) |
| Use your own script | `python make_short.py "topic" --script-file myscript.txt` |

## Keep your keys private
Never share or upload the `.env` file. If a key ever leaks, delete it on the Google or Pixabay website and make a new one.
