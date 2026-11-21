import csv
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, render_template, request, send_from_directory, abort
import yt_dlp

from uploader import YouTubeUploader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIPS_DIR = os.path.join(BASE_DIR, "clips")
os.makedirs(CLIPS_DIR, exist_ok=True)


def find_ffmpeg():
    system = shutil.which("ffmpeg")
    if system:
        return system
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


FFMPEG = find_ffmpeg()

AUTO_BROWSERS = ("brave", "firefox", "edge", "chrome", "opera")

W, H = 1080, 1920
VIDEO_FILTERS = {
    # Blurred copy of the frame fills the 9:16 background, full gameplay sits in the middle.
    # Background is blurred at 1/4 resolution then upscaled — same look, far less CPU.
    "blur": (
        f"fps=30,split[a][b];"
        f"[a]scale={W // 4}:{H // 4}:force_original_aspect_ratio=increase,crop={W // 4}:{H // 4},"
        f"boxblur=6:2,scale={W}:{H}[bg];"
        f"[b]scale={W}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    ),
    "crop": f"fps=30,crop=ih*9/16:ih,scale={W}:{H},setsar=1",
    "zoom": f"fps=30,scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1",
}


def safe_name(text, limit=40):
    text = re.sub(r"[^\w\- ]+", "", text or "stream", flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", text)[:limit] or "stream"


class Recorder:
    def __init__(self):
        self.lock = threading.Lock()
        self.proc = None
        self.thread = None
        self.stop_event = threading.Event()
        self.state = "idle"
        self.title = ""
        self.session_dir = None
        self.error = ""
        self.browser = ""
        self.log = deque(maxlen=60)

    def _log(self, msg):
        self.log.append(f"[{datetime.now():%H:%M:%S}] {msg}")

    def start(self, url, seconds, mode, quality):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("A recording is already running. Stop it first.")
            self.stop_event.clear()
            self.error = ""
            self.title = ""
            self.log.clear()
            self.state = "starting"
            self.thread = threading.Thread(
                target=self._run, args=(url, seconds, mode, quality), daemon=True
            )
            self.thread.start()

    def stop(self):
        self.stop_event.set()
        proc = self.proc
        if proc and proc.poll() is None:
            self._log("Stop requested: finalizing the current clip...")
            try:
                proc.stdin.write("q")
                proc.stdin.flush()
            except Exception:
                proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()

    def _extract(self, url, quality):
        fmt = (
            f"best[height<={quality}][protocol^=m3u8]/"
            f"bestvideo[height<={quality}]+bestaudio/"
            f"best[height<={quality}]/best"
        )
        base = {"format": fmt, "quiet": True, "no_warnings": True, "noplaylist": True}
        if shutil.which("node"):
            base["js_runtimes"] = {"node": {}}

        cookie_file = os.path.join(BASE_DIR, "cookies.txt")
        if os.path.exists(cookie_file):
            attempts = [("cookies.txt", {"cookiefile": cookie_file})]
        elif self.browser:
            attempts = [(self.browser, {"cookiesfrombrowser": (self.browser,)})]
        else:
            attempts = [("no cookies", {})] + [
                (b, {"cookiesfrombrowser": (b,)}) for b in AUTO_BROWSERS
            ]

        last_err = None
        for label, extra in attempts:
            try:
                with yt_dlp.YoutubeDL({**base, **extra}) as ydl:
                    info = ydl.extract_info(url, download=False)
                if extra.get("cookiesfrombrowser"):
                    self.browser = label
                    self._log(f"Stream found using {label} browser cookies.")
                return info
            except Exception as e:
                last_err = e
                if len(attempts) > 1:
                    self._log(f"{label}: failed, trying next option...")
        raise last_err

    def _completed_count(self):
        return len(list_clips(self.session_dir))

    def _build_cmd(self, info, seconds, mode, start_number):
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "warning", "-stats", "-y"]
        formats = info.get("requested_formats") or [info]
        for f in formats:
            headers = "".join(f"{k}: {v}\r\n" for k, v in (f.get("http_headers") or {}).items())
            if headers:
                cmd += ["-headers", headers]
            cmd += ["-i", f["url"]]

        if len(formats) > 1:
            cmd += ["-map", "0:v:0", "-map", "1:a:0?"]
        else:
            cmd += ["-map", "0:v:0", "-map", "0:a:0?"]

        out_pattern = os.path.join(self.session_dir, "clip_%04d.mp4")
        cmd += [
            "-vf", VIDEO_FILTERS.get(mode, VIDEO_FILTERS["blur"]),
            "-c:v", "libx264", "-preset", "superfast", "-crf", "22", "-pix_fmt", "yuv420p",
            "-force_key_frames", f"expr:gte(t,n_forced*{seconds})",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
            "-f", "segment",
            "-segment_time", str(seconds),
            "-segment_time_delta", "0.2",
            "-segment_start_number", str(start_number),
            "-segment_list", os.path.join(self.session_dir, "clips.csv"),
            "-segment_list_type", "csv",
            "-segment_list_flags", "+live",
            "-segment_format_options", "movflags=+faststart",
            "-reset_timestamps", "1",
            out_pattern,
        ]
        return cmd

    def _run(self, url, seconds, mode, quality):
        try:
            retries = 0
            while not self.stop_event.is_set():
                self.state = "fetching"
                self._log("Fetching stream info (yt-dlp)...")
                info = self._extract(url, quality)
                is_live = bool(info.get("is_live"))

                if self.session_dir is None or not self.title:
                    self.title = info.get("title") or "stream"
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    self.session_dir = os.path.join(CLIPS_DIR, f"{stamp}_{safe_name(self.title)}")
                    os.makedirs(self.session_dir, exist_ok=True)
                    self._log(f"Title: {self.title} | Live: {'Yes' if is_live else 'No (regular video)'}")
                    self._log(f"Clips folder: {self.session_dir}")

                cmd = self._build_cmd(info, seconds, mode, self._completed_count())
                self.state = "recording"
                self._log(f"Recording started — a 9:16 clip will be created every {seconds}s.")
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                last_stat = 0.0
                for line in self.proc.stderr:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("frame=") or "time=" in line:
                        if time.time() - last_stat > 5:
                            self._log(line)
                            last_stat = time.time()
                    else:
                        self._log(line)
                code = self.proc.wait()
                self.proc = None

                if self.stop_event.is_set():
                    break
                if not is_live:
                    self._log("Video finished — all clips created.")
                    break
                retries += 1
                if retries > 20:
                    raise RuntimeError("Stream connection keeps dropping, giving up.")
                self._log(f"ffmpeg stopped (code {code}). Reconnecting in 5s... ({retries})")
                time.sleep(5)
            self.state = "stopped"
            self._log("Recording stopped.")
        except Exception as e:
            self.error = str(e)
            self.state = "error"
            self._log(f"ERROR: {e}")
        finally:
            self.proc = None

    def status(self):
        return {
            "state": self.state,
            "title": self.title,
            "error": self.error,
            "session": os.path.basename(self.session_dir) if self.session_dir else None,
            "folder": self.session_dir,
            "log": list(self.log),
        }


def list_clips(session_dir):
    if not session_dir:
        return []
    csv_path = os.path.join(session_dir, "clips.csv")
    if not os.path.exists(csv_path):
        return []
    clips, seen = [], set()
    with open(csv_path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.reader(fh):
            if not row or row[0] in seen:
                continue
            name = os.path.basename(row[0])
            path = os.path.join(session_dir, name)
            if not os.path.exists(path):
                continue
            seen.add(row[0])
            clips.append({"name": name, "size_mb": round(os.path.getsize(path) / 1048576, 1)})
    return clips


app = Flask(__name__)
recorder = Recorder()
uploader = YouTubeUploader(
    BASE_DIR,
    get_session_dir=lambda: recorder.session_dir,
    get_stream_title=lambda: recorder.title,
    list_clips=list_clips,
    log=recorder._log,
)


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/start")
def api_start():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not re.match(r"^https?://", url):
        return jsonify(error="Please enter a valid YouTube link."), 400
    seconds = max(5, min(180, int(data.get("seconds", 30))))
    mode = data.get("mode", "blur")
    quality = int(data.get("quality", 1080))
    browser = data.get("browser", "")
    recorder.browser = browser if browser in ("firefox", "chrome", "edge", "brave", "opera") else ""
    recorder.session_dir = None
    try:
        recorder.start(url, seconds, mode, quality)
    except RuntimeError as e:
        return jsonify(error=str(e)), 409
    return jsonify(ok=True)


@app.post("/api/stop")
def api_stop():
    threading.Thread(target=recorder.stop, daemon=True).start()
    return jsonify(ok=True)


@app.get("/api/status")
def api_status():
    st = recorder.status()
    st["clips"] = list_clips(recorder.session_dir)
    for clip in st["clips"]:
        clip["upload"] = uploader.clip_state(clip["name"])
    st["youtube"] = uploader.status()
    return jsonify(st)


@app.post("/api/youtube/connect")
def api_youtube_connect():
    try:
        uploader.connect()
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    return jsonify(ok=True)


@app.post("/api/youtube/disconnect")
def api_youtube_disconnect():
    uploader.disconnect()
    return jsonify(ok=True)


@app.post("/api/youtube/settings")
def api_youtube_settings():
    uploader.update_settings(request.get_json(force=True))
    return jsonify(ok=True)


def _clip_name_or_error(name):
    name = os.path.basename(name or "")
    if not recorder.session_dir or not os.path.exists(os.path.join(recorder.session_dir, name)):
        return None, (jsonify(error="Clip not found."), 404)
    return name, None


@app.get("/api/youtube/meta")
def api_youtube_meta():
    name, err = _clip_name_or_error(request.args.get("name"))
    if err:
        return err
    meta = uploader.default_metadata(name)
    st = uploader.clip_state(name) or {}
    meta["title"] = st.get("title", meta["title"])
    meta["description"] = st.get("description", meta["description"])
    meta["privacy"] = uploader.settings["privacy"]
    return jsonify(meta)


@app.post("/api/youtube/approve")
def api_youtube_approve():
    data = request.get_json(force=True)
    name, err = _clip_name_or_error(data.get("name"))
    if err:
        return err
    if not uploader.enabled:
        return jsonify(error="YouTube upload is disabled."), 400
    if not uploader.connected:
        return jsonify(error="Connect your YouTube account first."), 400
    uploader.enqueue(name, title=data.get("title"), description=data.get("description"))
    return jsonify(ok=True)


@app.post("/api/youtube/reject")
def api_youtube_reject():
    name, err = _clip_name_or_error(request.get_json(force=True).get("name"))
    if err:
        return err
    uploader.reject(name)
    return jsonify(ok=True)


@app.post("/api/youtube/resume")
def api_youtube_resume():
    uploader.resume()
    return jsonify(ok=True)


@app.post("/api/open-folder")
def api_open_folder():
    folder = recorder.session_dir or CLIPS_DIR
    if os.name == "nt":
        os.startfile(folder)
    return jsonify(ok=True)


@app.get("/clips/<session>/<name>")
def serve_clip(session, name):
    folder = os.path.join(CLIPS_DIR, os.path.basename(session))
    if not os.path.isdir(folder):
        abort(404)
    as_attachment = request.args.get("dl") == "1"
    return send_from_directory(folder, os.path.basename(name), as_attachment=as_attachment)


if __name__ == "__main__":
    print(f"ffmpeg: {FFMPEG}")
    print("Open in browser: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
