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
├── templates\index.html # Web UI
├── requirements.txt
├── start.bat            # One-click setup + run
└── clips\               # Generated reels
```
