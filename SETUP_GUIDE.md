# Setup & Use Guide — GTA Live → 9:16 Reels Clipper

A step-by-step guide to install the tool on your own Windows PC, make 9:16 reel clips from a YouTube live stream, and (optionally) upload them to your YouTube channel.

- [1. What you need](#1-what-you-need)
- [2. Get the project](#2-get-the-project)
- [3. Install and start](#3-install-and-start)
- [4. Make your first clips](#4-make-your-first-clips)
- [5. Set up YouTube upload (one time)](#5-set-up-youtube-upload-one-time)
- [6. Upload clips to YouTube](#6-upload-clips-to-youtube)
- [7. Everyday use (quick checklist)](#7-everyday-use-quick-checklist)
- [8. Where files are saved](#8-where-files-are-saved)
- [9. Troubleshooting](#9-troubleshooting)
- [10. Update, stop, uninstall](#10-update-stop-uninstall)

---

## 1. What you need

| Requirement | Why | Get it |
| --- | --- | --- |
| Windows 10 / 11 | The tool is built and tested on Windows | — |
| Python 3.10 or newer | Runs the tool | [python.org/downloads](https://www.python.org/downloads/) — tick **"Add Python to PATH"** in the installer |
| Node.js (recommended) | Lets yt-dlp read all YouTube stream formats | [nodejs.org](https://nodejs.org/) (LTS) |
| Git (optional) | To download / update the project | [git-scm.com](https://git-scm.com/download/win) |
| A browser logged in to YouTube | YouTube asks for cookies ("not a bot" check) | **Brave** or **Firefox** work best |

You do **not** need to install ffmpeg — it is bundled automatically.

Check Python is installed: open **PowerShell** and run

```powershell
python --version
```

You should see `Python 3.10` or higher.

## 2. Get the project

**With Git:**

```powershell
cd D:\
git clone https://github.com/thansingh2000/GTA-live-Reels-Clipper.git tool
cd tool
```

**Without Git:** open the GitHub page → **Code → Download ZIP**, then extract it (for example to `D:\tool`).

## 3. Install and start

### Easy way (recommended)

Double-click **`start.bat`** in the project folder. The first run takes a few minutes. It:

1. creates a private Python environment (`venv` folder),
2. installs all dependencies,
3. opens **http://127.0.0.1:5000** in your browser and starts the tool.

Keep the black console window open while you use the tool — closing it stops the tool.

> If the browser opens before the tool is ready, just refresh the page after a few seconds.

### Manual way

```powershell
cd D:\tool
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
pip install -U "yt-dlp[default]"
python app.py
```

Then open **http://127.0.0.1:5000**.

The console shows which video encoder is used, for example `Video encoder: Intel GPU (Quick Sync)`. The tool picks the fastest one automatically: NVIDIA → Intel → AMD → CPU.

## 4. Make your first clips

1. **YouTube Live / Video link** — paste the link of the live stream (a normal video also works).
2. **Clip length** — 15 to 90 seconds per clip.
3. **9:16 Style**
   - **Full gameplay + blur background** — the whole game screen in the middle, blurred fill above and below. Best for reels.
   - **Center crop** — the center of the screen fills the whole reel.
   - **Zoom fill** — zooms in until the screen is filled.
4. **Quality (max)** — 4K, 1440p, 1080p, 720p or 480p. You only get 4K / 1440p if the stream itself is broadcast in that quality. On live streams, 4K needs Center crop or Zoom fill; with blur the tool uses 1440p so it can keep up.
5. **Stop after (clips)** — for example `10` makes exactly 10 clips and stops by itself. `0` = no limit.
6. **YouTube cookies** — leave on **Auto**. The tool tries every browser until one works. Make sure you are logged in to YouTube in that browser.
7. **Auto-download** — tick it to have every clip downloaded by the browser as soon as it is ready. The first time, the browser asks to allow **multiple downloads** → click **Allow**.
8. Click **▶ Start**.

The first clip appears after about one clip length. Each clip shows a preview, its size and a **⬇** download button. Click **■ Stop** at any time — the clip in progress is finished and saved.

**Watch the speed:** the log shows lines like `speed=1.15x`. It must stay **above 1x** for a live stream. If it drops below 1x, pick a lower quality or the Center crop style.

## 5. Set up YouTube upload (one time)

Skip this section if you only want to download clips.

### 5.1 Create the Google Cloud project

1. Open [console.cloud.google.com](https://console.cloud.google.com/) and log in.
2. Top bar → project picker → **New project** → give it a name (e.g. your channel name) → **Create**, then select it.

### 5.2 Enable the YouTube Data API

1. Menu → **APIs & Services → Library**.
2. Search **YouTube Data API v3** → open it → **Enable**.

> If you skip this, connecting works but the tool shows *"YouTube Data API v3 is not enabled"*.

### 5.3 Configure the consent screen and add yourself as a test user

1. Menu → **Google Auth Platform** (older layout: **APIs & Services → OAuth consent screen**).
2. Fill in the app name and your email. User type / audience: **External**.
3. Go to **Audience → Test users → + Add users** and add the **Gmail address that owns your YouTube channel**. Save.
4. Leave the publishing status on **Testing** (do not click "Publish app").

> If you skip the test user step, Google shows *"Access blocked: … has not completed the Google verification process" (Error 403: access_denied)*.

### 5.4 Create the OAuth client

1. **Google Auth Platform → Clients** (older layout: **APIs & Services → Credentials → Create credentials → OAuth client ID**).
2. Application type: **Desktop app** → **Create**.
3. **Download JSON** and save the file as **`client_secret.json`** inside the project folder (next to `app.py`).

Never share or upload this file — it is already excluded from Git.

### 5.5 Connect the tool

1. Restart the tool (close the console window, run `start.bat` again).
2. In the **▶ YouTube upload** panel turn the switch **On**.
3. Click **Connect YouTube** — a Google login page opens.
4. Choose the channel's Gmail account.
5. *"Google hasn't verified this app"* → click **Continue** (it is your own app).
6. Allow the YouTube permissions → **Continue**.
7. *"YouTube connected. You can close this tab."* → close the tab.

The panel now shows **Connected: \<your channel\>**. The login is saved in `token.json`, so you only do this once. Finish the Google screens within 2 minutes; otherwise click **Try again**.

### 5.6 Optional: verify your channel

Custom thumbnails only work on a phone-verified channel: [youtube.com/verify](https://www.youtube.com/verify).

## 6. Upload clips to YouTube

### Settings (YouTube panel)

| Setting | What it does |
| --- | --- |
| **YouTube upload switch** | Off = the tool only saves/downloads clips, exactly like before. On = upload options appear. |
| **✨ SEO mode** | Generates a keyword-optimized title (hook + keyword + `#Shorts`), description with hashtags, and tags for every clip. |
| **Focus keywords** | Your main keywords, most important first (e.g. `GTA 6, Vice City, Police Chase`). Empty = detected from the stream title. |
| **Privacy** | Public (default), Unlisted or Private. |
| **Extra tags** | Added to every clip. |
| **Automatically upload every new clip** | Picks up every clip made *after* you tick it. |
| **Daily upload limit** | 1–50 (default 5). Extra clips wait in the queue for the next day. |
| **Review each clip before it uploads** | New clips wait for your approval in the preview popup (recommended). |
| **📅 Publish on a daily schedule (IST)** | Upload anytime — each clip is published at the next free slot (default 6:30 AM, 12:30 PM, 7:30 PM). Edit the slot times, themes and SEO keywords in the panel. |

### Review popup

Click **Review now** (banner above the clips), or **⬆ Upload / Review** on any clip:

1. Watch the clip.
2. Edit the **title** (max 100 characters), **description** and **tags** (max 500 characters), or click **✨ New SEO idea** for another version.
3. **Thumbnail (optional):** pause the video on the best moment → **📸 Use current video frame**, or **🖼 Upload image**.
4. **📅 Publish time:** the next free slot is pre-selected; pick another slot or **Publish immediately**. The SEO title follows the slot's theme.
5. Click **✅ Approve & Upload**. A loader and progress bar show the upload; when it finishes you get **🎉 Uploaded to YouTube!** (or **📅 Uploaded & scheduled!** with the publish time) plus **Open on YouTube**, **Copy link** and **Review next**.
6. Or click **🚫 Skip this clip** / **Decide later**.

Each clip card always shows its status: waiting for review, queued, uploading %, uploaded (with link), skipped, or the error with **Retry**.

### YouTube limits to know

- **About 6 uploads per day** with a new Google Cloud project (10,000 quota units per day, one upload ≈ 1,600). Keep the daily limit at **5**. The day resets at **midnight Pacific time ≈ 1:30 PM IST**.
- Videos from an **unverified** Google app may be **locked to Private** by YouTube even if you choose Public — this also stops **scheduled** videos from going public. Check one upload in YouTube Studio; if it says *"Private (locked)"* / restricted, apply for the free [YouTube API Services audit](https://support.google.com/youtube/contact/yt_api_form) so scheduling works automatically.
- Uploading clips of **someone else's stream** can cause copyright claims. Only use streams you own or have permission for.

## 7. Everyday use (quick checklist)

1. Double-click **`start.bat`**.
2. Paste the live link, choose clip length / style / quality / stop-after.
3. **Start**.
4. YouTube upload on? Click **Review now** whenever clips are waiting → check → **Approve & Upload**.
5. **Stop** when done (or let *Stop after* do it), then close the console window.

## 8. Where files are saved

| What | Location |
| --- | --- |
| Clips | `clips\<date_time>_<stream title>\clip_0000.mp4, clip_0001.mp4, …` (also opened by **📁 Open folder**) |
| Thumbnails you chose | `clips\<session>\thumbs\` |
| Upload status per clip | `clips\<session>\uploads.json` |
| YouTube login | `token.json` (delete it or click **Disconnect** to log out) |
| YouTube settings | `yt_settings.json` |
| Uploads counted today | `upload_counts.json` |

## 9. Troubleshooting

| Problem | Fix |
| --- | --- |
| `python` is not recognized | Reinstall Python and tick **Add Python to PATH**, then open a new PowerShell window. |
| Page doesn't open / "This site can't be reached" | Make sure the console window from `start.bat` is still open, then refresh http://127.0.0.1:5000. |
| `Sign in to confirm you're not a bot` | Log in to YouTube in Brave or Firefox and keep cookies on **Auto** (or pick that browser). Still failing: export cookies with the "Get cookies.txt LOCALLY" extension and save as `cookies.txt` in the project folder. |
| `Could not copy Chrome cookie database` | Chrome/Edge cookies can't be read while the browser is open. Use Brave/Firefox or `cookies.txt`. |
| `speed=` below 1x in the log | Lower the quality, or use Center crop. Updating your GPU driver can enable a faster encoder. |
| NVIDIA GPU not used | The NVIDIA driver is too old for the bundled ffmpeg — update it from [nvidia.com/drivers](https://www.nvidia.com/drivers); the tool uses NVENC automatically afterwards. |
| *Access blocked … has not completed the Google verification process* | Add your Gmail under **Test users** (section 5.3). |
| *YouTube Data API v3 is not enabled* | Enable it (section 5.2); the tool reconnects by itself within 30 seconds. |
| Connect button stuck on "Waiting for Google login" | Click **Try again** and finish the Google screens within 2 minutes. |
| `client_secret.json not found` | Download the OAuth client JSON (section 5.4) and save it with exactly that name next to `app.py`. |
| *Daily limit reached* | Wait for the reset (shown in the panel) or raise the daily limit — staying under ~6 avoids Google's quota error. |
| *YouTube API daily upload quota reached* | Google's quota is used up; click **Retry now** after the reset. |
| Thumbnail: *verify your channel* | Verify the channel at [youtube.com/verify](https://www.youtube.com/verify). The video itself is uploaded anyway. |
| Video uploaded as Private although Public was chosen | Normal for unverified Google apps — change it in YouTube Studio. |
| Sudden YouTube errors after it worked before | YouTube changed something — run `start.bat` again (it updates yt-dlp). |

## 10. Update, stop, uninstall

- **Stop the tool:** click **■ Stop** (if recording), then close the console window.
- **Update:** in the project folder run `git pull`, then start with `start.bat` (dependencies update automatically).
- **Log out of YouTube:** **Disconnect** in the YouTube panel.
- **Uninstall:** delete the project folder. To revoke the tool's access to your Google account completely, remove it at [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
