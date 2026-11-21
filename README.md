# GTA Live → 9:16 Reels Clipper

Paste a YouTube live (or regular video) link — the tool records the stream, cuts it into **1080x1920 (9:16) reel clips** every N seconds, and downloads them automatically in your browser.

## Requirements

- Windows 10/11
- [Python 3.10+](https://www.python.org/downloads/) (tick **"Add Python to PATH"** during install)
- [Node.js](https://nodejs.org/) (recommended — yt-dlp uses it to get all YouTube formats)
- A browser where you are **logged in to YouTube** (Brave or Firefox work best)

No separate `ffmpeg` install is needed — the `imageio-ffmpeg` package ships its own binary.

## Setup + Run (easy way)

Double-click `start.bat`. It will:

1. Create a `venv` (first run only)
2. Install / update all dependencies
3. Start the server and open http://127.0.0.1:5000 in your browser

## Setup + Run (manual)

```powershell
cd d:\tool
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
pip install -U "yt-dlp[default]"
python app.py
```

Then open: http://127.0.0.1:5000

## How to use

1. Paste the YouTube live link.
2. Choose the **Clip length** (15–90 sec).
3. Choose the **9:16 Style**:
   - **Full gameplay + blur background** — full gameplay in the middle, blurred fill above and below (best for reels)
   - **Center crop** — the center of the frame, full screen
   - **Zoom fill** — zooms the frame to fill the screen
4. **Source quality** — pick 720p on a slower PC.
5. **YouTube cookies** — leave on "Auto"; the tool finds a working browser by itself.
6. Press **Start**. Each clip shows up in the UI with a preview and is auto-downloaded.
   - The first time, the browser asks permission for "multiple downloads" → click **Allow**.
7. Press **Stop** — the clip in progress is saved before recording ends.

All clips are also saved here:

```
d:\tool\clips\<date_time>_<stream_title>\clip_0000.mp4, clip_0001.mp4, ...
```

The **📁 Open folder** button in the UI opens it directly.

## YouTube auto-upload

The tool can upload every finished clip to your YouTube channel as a Short (vertical, under 3 minutes) using the official YouTube Data API v3.

### One-time setup

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **APIs & Services → OAuth consent screen** → User type **External** → fill in the app name and your email → under **Test users** add the Google account that owns your YouTube channel.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Desktop app**.
5. Download the JSON and save it as `d:\tool\client_secret.json`.
6. Restart the tool, click **Connect YouTube** in the UI, and log in with your channel's account. (Google shows an "app isn't verified" warning for your own test app — click **Continue**.)

The login is saved in `token.json`, so you only do this once.

### Using it

- Turn on the **YouTube upload** switch. When it is off (the default), the tool works exactly like before: clips are only saved and downloaded, and no upload options or buttons are shown.
- Set the **Daily upload limit** (1–50, default 5) right in the UI.
- Set the **title template** (`{n}` = clip number, `{stream}` = stream title, `{date}` = today), description, tags and privacy.
- Tick **Automatically upload every new clip** — every clip finished *after* you tick it is picked up.
- **Review each clip before it uploads** (on by default): new clips wait as "👀 Waiting for review". Click **Review now** (or **Review** on a clip) to open a preview popup where you watch the clip, edit its title/description, and choose **✅ Approve & Upload**, **🚫 Skip this clip**, or **Decide later**. After each decision the next waiting clip opens automatically. Turn this option off to upload new clips without asking.
- Any clip (including older or skipped ones) can be uploaded with its **⬆ Upload** button — it opens the same preview popup first. Failed uploads show a **Retry** button.
- Each clip card shows its status: waiting for review, skipped, queued, uploading %, uploaded (with link), or the error.

### Important YouTube limits

- **Daily quota:** a new Google Cloud project gets 10,000 API units/day and one upload costs ~1,600, so only **about 6 uploads per day**. The tool therefore caps uploads at **5 per day** by default (change it with **Daily upload limit** in the UI), counted on the same day boundary as the quota (midnight Pacific time ≈ 1:30 PM IST). Extra clips stay queued and upload automatically after the reset. If Google still reports the quota as exhausted, uploads pause — press **Retry now** later. For more uploads, request a quota increase from Google.
- **Private lock for unverified apps:** videos uploaded through an API project that hasn't passed Google's audit may be locked to **Private**, whatever privacy you choose. To publish them, change visibility in YouTube Studio or get the project audited by Google.
- Uploading clips of someone else's stream can trigger **copyright claims** — only upload streams you own or have permission to use.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `Sign in to confirm you're not a bot` | Log in to YouTube in your browser and keep cookies on "Auto" (or pick the browser). If it still fails, use the `cookies.txt` method below. |
| `Could not copy Chrome cookie database` | yt-dlp can't read Chrome/Edge cookies. Use Brave or Firefox, or `cookies.txt`. |
| `speed=` below 1x in the log | Your PC is falling behind the live stream — switch to 720p or the "Center crop" style. |
| Stream stopped | The tool reconnects automatically after 5 seconds and continues the clip numbering. |
| YouTube extraction errors suddenly appear | Run `.\venv\Scripts\pip install -U "yt-dlp[default]"` (or just run `start.bat` again). |

### cookies.txt method

1. Install the "Get cookies.txt LOCALLY" browser extension.
2. Open youtube.com (logged in) and export the cookies.
3. Save the file as `d:\tool\cookies.txt` — the tool picks it up automatically.

## Project structure

```
d:\tool
├── app.py               # Flask backend: yt-dlp + ffmpeg recording / clipping
├── uploader.py          # YouTube Data API upload queue
├── templates\index.html # Web UI
├── requirements.txt
├── start.bat            # One-click setup + run
└── clips\               # Generated reels
```
