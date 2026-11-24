# Phase 2: Automatic daily posting

Once this is set up, GitHub runs the bot every day for free, even when your Mac is off. Each day it:
1. Asks Gemini for a fresh topic in your niche (never repeats a topic)
2. Makes the Short
3. Uploads it to YouTube and TikTok
4. Saves a copy you can download for 14 days

You only do the steps below once.

---

## A. GitHub (where the bot lives)
1. Go to https://github.com/new
2. Repository name: `shorts-bot`. Choose **Private**. Leave everything else as it is and click **Create repository**.
3. Give Claude access: go to https://github.com/apps/claude, click **Configure**, choose your account, select **Only select repositories**, pick `shorts-bot` and click **Save**.
4. Tell Claude your GitHub username. Claude uploads the code.

## B. YouTube (one-time sign-in)
1. Go to https://console.cloud.google.com and sign in with the Google account that owns your YouTube channel.
2. At the top, click the project picker, then **New project**. Name it `Shorts Bot` and click **Create**, then make sure it's selected.
3. Search the top bar for **YouTube Data API v3**, open it and click **Enable**.
4. Search for **Google Auth Platform** (it may be called "OAuth consent screen") and click **Get started**:
   - App name: `Shorts Bot`. Support email: your email.
   - Audience: **External**. Contact email: your email. Agree to the terms and click **Create**.
5. In the left menu, click **Audience**, then **Publish app**, then **Confirm**.
   This is important: if you skip it, the sign-in stops working after 7 days.
6. In the left menu, click **Clients**, then **Create client**:
   - Application type: **Desktop app**. Name: `Shorts Bot`. Click **Create**.
   - Click **Download JSON**. Move the downloaded `client_secret_....json` file into your `shorts-bot` folder on your Mac.
7. On your Mac, open Terminal (press Cmd+Space, type Terminal, press Enter) and run:
   ```
   cd ~/Documents/shorts-bot
   source venv/bin/activate
   pip install -r requirements.txt
   python connect_youtube.py
   ```
   A browser opens. Pick your channel's account. You'll see a warning that says **"Google hasn't verified this app"**. That's expected, because it's your own app: click **Advanced**, then **Go to Shorts Bot**, then **Continue**.
   The Terminal then shows three values. Keep that window open for step D.

### Making YouTube uploads public
Google locks uploads from new, unreviewed projects as **private**. To unlock public posting, fill in the free audit form at https://support.google.com/youtube/contact/yt_api_form. Describe it as *"a personal tool that uploads my own videos to my own channel"*. Until it's approved, the bot uploads privately, and you make each video public in YouTube Studio with two taps.

## C. TikTok
TikTok makes every developer app go through a review. Until your app passes, posts are forced to "only me".
1. Go to https://developers.tiktok.com and log in with your TikTok account, then click **Manage apps** and **Connect an app**.
2. Fill in the app details. TikTok asks for a website, a **Terms of Service** URL and a **Privacy Policy** URL. Claude can create simple pages for those, so just ask when you get here.
3. Click **Add products** and add:
   - **Login Kit**. For the Redirect URI, use your Privacy Policy page's URL.
   - **Content Posting API**. Turn on **Direct Post**.
4. Under Scopes, make sure `user.info.basic`, `video.upload` and `video.publish` are ticked.
5. Copy the **Client key** and **Client secret** into your `.env` on your Mac, plus the redirect URI:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   TIKTOK_REDIRECT_URI=https://...the same URL as in step 3...
   ```
6. Run `python connect_tiktok.py` and follow what it prints.
7. Click **Submit for review**. Once TikTok approves it, set `TIKTOK_PRIVACY` to `PUBLIC_TO_EVERYONE` (see step D).

## D. Put your keys into GitHub's vault
On GitHub, open your `shorts-bot` repository and go to **Settings**, then **Secrets and variables**, then **Actions**.

**Secrets** tab: click **New repository secret** for each one below. Paste the name exactly as written, then the value.

| Name | Value |
|---|---|
| `GEMINI_API_KEY` | your Gemini key |
| `PIXABAY_API_KEY` | your Pixabay key |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | from step B7 |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` | from step C |

**Variables** tab: click **New repository variable** for each:

| Name | Value |
|---|---|
| `NICHE` | your channel theme, e.g. `mind-blowing ocean and nature facts` |
| `YT_PRIVACY` | `private` for now. Change it to `public` once the YouTube audit is approved. |
| `TIKTOK_PRIVACY` | `SELF_ONLY` for now. Change it to `PUBLIC_TO_EVERYONE` once TikTok approves your app. |

## E. Test it
On GitHub, open the **Actions** tab and click **Daily Short**, then **Run workflow**. About 5 to 15 minutes later, the video appears on YouTube (as private) and in TikTok. From then on it runs by itself every day at 15:37 UTC.

If a run fails, GitHub emails you. Open the run on the **Actions** tab and send Claude the red error lines.
