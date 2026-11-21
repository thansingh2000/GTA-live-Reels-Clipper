import base64
import binascii
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
QUALITIES = (2160, 1440, 1080, 720, 480)
# Vertical output size picked from the real source height (never upscale beyond the source).
OUTPUT_SIZES = ((2160, (2160, 3840)), (1440, (1440, 2560)), (0, (1080, 1920)))
LIVE_BLUR_MAX = (1440, 2560)

ENCODER_ARGS = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0", "-pix_fmt", "yuv420p"],
    "h264_qsv": ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "21", "-forced_idr", "1", "-pix_fmt", "nv12"],
    "h264_amf": ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "21", "-qp_p", "21", "-pix_fmt", "yuv420p"],
}
ENCODER_NAMES = {"h264_nvenc": "NVIDIA GPU (NVENC)", "h264_qsv": "Intel GPU (Quick Sync)",
                 "h264_amf": "AMD GPU (AMF)", "libx264": "CPU (x264)"}


def detect_encoder():
    for name in ENCODER_ARGS:
        try:
            probe = subprocess.run(
                [FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=s=1280x720:d=0.2",
                 *ENCODER_ARGS[name], "-f", "null", "-"],
                capture_output=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if probe.returncode == 0:
                return name
        except Exception:
            pass
    return "libx264"


ENCODER = detect_encoder()


def video_filter(mode, w, h):
    if mode == "crop":
        return f"fps=30,crop=ih*9/16:ih,scale={w}:{h}:flags=lanczos,setsar=1"
    if mode == "zoom":
        return f"fps=30,scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},setsar=1"
    # Blurred copy of the frame fills the 9:16 background, full gameplay sits in the middle.
    # Background is blurred at 1/4 resolution then upscaled — same look, far less CPU.
    return (
        f"fps=30,split[a][b];"
        f"[a]scale={w // 4}:{h // 4}:force_original_aspect_ratio=increase,crop={w // 4}:{h // 4},"
        f"boxblur=6:2,scale={w}:{h}[bg];"
        f"[b]scale={w}:-2:flags=lanczos[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


PART_FONT = next((f for f in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
                               "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                               "/Library/Fonts/Arial Bold.ttf") if os.path.exists(f)), None)


def part_label_filter(seconds, start_number, height):
    font = PART_FONT.replace("\\", "/").replace(":", "\\:")
    size = height // 16
    sub_size = height // 34
    style = "shadowx=3:shadowy=3:shadowcolor=black@0.6:bordercolor=black:x=(w-text_w)/2"
    # The 0.01 s nudge keeps the first frame of each segment (t == k*seconds exactly) on the new number.
    number = f"floor(t/{seconds}+0.01)+{start_number + 1}"
    part = (f"drawtext=fontfile='{font}':text='Part #%{{eif\\:{number}\\:d}}'"
            f":fontsize={size}:fontcolor=white:borderw={max(2, size // 12)}:{style}:y=h*0.07")
    subscribe = (f"drawtext=fontfile='{font}':text='Please Subscribe for next Part'"
                 f":fontsize={sub_size}:fontcolor=yellow:borderw={max(2, sub_size // 10)}:{style}"
                 f":y=h*0.07+{int(size * 1.35)}")
    return f"{part},{subscribe}"


def channel_filter(text_path, height):
    # Read from a file with expansion off so any channel name (quotes, colons, %) is drawn literally.
    # Kept above the bottom ~15% that the YouTube Shorts player covers with the title and buttons.
    font = PART_FONT.replace("\\", "/").replace(":", "\\:")
    path = text_path.replace("\\", "/").replace(":", "\\:")
    size = height // 26
    return (f"drawtext=fontfile='{font}':textfile='{path}':expansion=none"
            f":fontsize={size}:fontcolor=white:borderw={max(2, size // 10)}:bordercolor=black"
            f":shadowx=3:shadowy=3:shadowcolor=black@0.6:x=(w-text_w)/2:y=h*0.84-text_h")


def output_size(source_height):
    for min_height, size in OUTPUT_SIZES:
        if (source_height or 0) >= min_height:
            return size
    return OUTPUT_SIZES[-1][1]


def encoder_args(width):
    if ENCODER != "libx264":
        return ENCODER_ARGS[ENCODER]
    preset = "ultrafast" if width > 1080 else "superfast"
    return ["-c:v", "libx264", "-preset", preset, "-crf", "21", "-pix_fmt", "yuv420p"]


def fmt_duration(sec):
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


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
        self.max_clips = 0
        self.part_label = True
        self.channel_text = ""
        self.duration = 0
        self.progress = ""
        self.output = ""
        self.log = deque(maxlen=60)

    def _log(self, msg):
        msg = re.sub(r"(https?://[^\s'\"/]+)[^\s'\"]{40,}", r"\1/…", str(msg))
        self.log.append(f"[{datetime.now():%H:%M:%S}] {msg}")

    def start(self, url, seconds, mode, quality, max_clips=0, part_label=True, channel_text=""):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("A recording is already running. Stop it first.")
            self.stop_event.clear()
            self.error = ""
            self.title = ""
            self.output = ""
            self.max_clips = max_clips
            self.part_label = part_label
            self.channel_text = channel_text
            self.duration = 0
            self.progress = ""
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

    @staticmethod
    def _source_height(info):
        formats = info.get("requested_formats") or [info]
        return max((f.get("height") or 0) for f in formats) or info.get("height") or 0

    def _output_size(self, info, mode):
        size = output_size(self._source_height(info))
        # 4K blur can't keep up with a live stream on most PCs; 1440p blur can.
        if info.get("is_live") and mode == "blur" and size[0] > LIVE_BLUR_MAX[0]:
            return LIVE_BLUR_MAX
        return size

    def _build_cmd(self, info, seconds, mode, start_number):
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "warning", "-stats", "-y"]
        formats = info.get("requested_formats") or [info]
        width, height = self._output_size(info, mode)
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
        vf = video_filter(mode, width, height)
        if self.part_label and PART_FONT:
            vf += "," + part_label_filter(seconds, start_number, height)
        if self.channel_text and PART_FONT:
            text_path = os.path.join(self.session_dir, "channel_name.txt")
            with open(text_path, "w", encoding="utf-8") as fh:
                fh.write(self.channel_text)
            vf += "," + channel_filter(text_path, height)
        cmd += [
            "-filter_threads", str(os.cpu_count() or 4),
            "-vf", vf,
            *encoder_args(width),
            "-force_key_frames", f"expr:gte(t,n_forced*{seconds})",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        ]
        if self.max_clips:
            remaining = self.max_clips - start_number
            cmd += ["-t", str(remaining * seconds)]
        cmd += [
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

    def _track_progress(self, line, offset):
        match = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
        if not match or not self.duration:
            return
        h, m, s = match.groups()
        pos = min(self.duration, offset + int(h) * 3600 + int(m) * 60 + float(s))
        self.progress = (f"{fmt_duration(pos)} / {fmt_duration(self.duration)} "
                         f"({pos * 100 / self.duration:.0f}%)")

    def _run(self, url, seconds, mode, quality):
        try:
            retries = 0
            was_live = False
            while not self.stop_event.is_set():
                self.state = "fetching"
                self._log("Fetching stream info (yt-dlp)...")
                info = self._extract(url, quality)
                is_live = bool(info.get("is_live"))
                if was_live and not is_live:
                    # Once a live ends YouTube serves the full replay; re-reading it would clip everything again.
                    self._log("Live stream has ended — clipping stopped.")
                    break
                was_live = is_live
                self.duration = 0 if is_live else (info.get("duration") or 0)

                if self.session_dir is None or not self.title:
                    self.title = info.get("title") or "stream"
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    self.session_dir = os.path.join(CLIPS_DIR, f"{stamp}_{safe_name(self.title)}")
                    os.makedirs(self.session_dir, exist_ok=True)
                    self._log(f"Title: {self.title} | Live: {'Yes' if is_live else 'No (regular video)'}")
                    self._log(f"Clips folder: {self.session_dir}")

                done = self._completed_count()
                if self.max_clips and done >= self.max_clips:
                    self._log(f"Reached the limit of {self.max_clips} clips.")
                    break
                cmd = self._build_cmd(info, seconds, mode, done)
                src_h = self._source_height(info)
                out_w, out_h = self._output_size(info, mode)
                self.output = f"{src_h or '?'}p source → {out_w}x{out_h} · {ENCODER_NAMES[ENCODER]}"
                if src_h and src_h < quality:
                    self._log(f"Note: the stream only offers {src_h}p, so {quality}p is not available.")
                if (out_w, out_h) == LIVE_BLUR_MAX and output_size(src_h)[0] > out_w:
                    self._log("4K + blur is too heavy for live — using 1440p. Pick Center crop / Zoom fill for 4K live.")
                self.state = "recording"
                limit_txt = f", stopping after {self.max_clips} clips" if self.max_clips else ""
                self._log(f"Recording started — a 9:16 clip every {seconds}s{limit_txt}. {self.output}")
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
                        self._track_progress(line, done * seconds)
                        if time.time() - last_stat > 5:
                            self._log(line + (f" · {self.progress}" if self.progress else ""))
                            last_stat = time.time()
                    else:
                        self._log(line)
                code = self.proc.wait()
                self.proc = None

                if self.stop_event.is_set():
                    break
                if self.max_clips and self._completed_count() >= self.max_clips:
                    self._log(f"Done — {self.max_clips} clips created, recording stopped automatically.")
                    break
                if not is_live:
                    if code == 0:
                        total = fmt_duration(self.duration)
                        self.progress = f"{total} / {total} (100%)" if self.duration else ""
                        self._log("Video finished — all clips created, clipping stopped.")
                    else:
                        self._log(f"ffmpeg stopped with an error (code {code}) before the video ended.")
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
            "max_clips": self.max_clips,
            "output": self.output,
            "progress": self.progress,
            "encoder": ENCODER_NAMES[ENCODER],
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
    if quality not in QUALITIES:
        quality = 1080
    try:
        max_clips = max(0, min(1000, int(data.get("max_clips") or 0)))
    except ValueError:
        max_clips = 0
    browser = data.get("browser", "")
    recorder.browser = browser if browser in ("firefox", "chrome", "edge", "brave", "opera") else ""
    recorder.session_dir = None
    try:
        channel_text = ""
        if data.get("channel_label", True):
            channel_text = (data.get("channel_text") or "").strip()[:60] or uploader.channel or ""
        recorder.start(url, seconds, mode, quality, max_clips,
                       part_label=bool(data.get("part_label", True)), channel_text=channel_text)
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
    variant = request.args.get("variant", type=int)
    slots = uploader.free_slots(6)
    wanted = request.args.get("slot")
    slot = None if wanted == "now" else next((s for s in slots if s["key"] == wanted), slots[0] if slots else None)
    meta = uploader.default_metadata(name, variant or 0, slot_keywords=slot["keywords"] if slot else "")
    st = uploader.clip_state(name) or {}
    if variant is None and wanted is None:
        for key in ("title", "description", "tags"):
            if key in st:
                meta[key] = st[key]
    meta["privacy"] = uploader.settings["privacy"]
    meta["seo_mode"] = uploader.settings["seo_mode"]
    meta["schedule"] = uploader.schedule_active
    meta["slots"] = slots
    meta["slot"] = slot["key"] if slot else "now"
    return jsonify(meta)


def _save_thumbnail(name, data_url):
    match = re.match(r"^data:image/(jpeg|jpg|png);base64,(.+)$", data_url or "", re.S)
    if not match:
        raise ValueError("Thumbnail must be a JPEG or PNG image.")
    raw = base64.b64decode(match.group(2))
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Thumbnail is larger than YouTube's 2 MB limit.")
    folder = os.path.join(recorder.session_dir, "thumbs")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, os.path.splitext(name)[0] + ".jpg")
    with open(path, "wb") as fh:
        fh.write(raw)
    return path


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
    thumbnail = None
    if data.get("thumbnail"):
        try:
            thumbnail = _save_thumbnail(name, data["thumbnail"])
        except (ValueError, binascii.Error) as e:
            return jsonify(error=str(e)), 400
    uploader.enqueue(name, title=data.get("title"), description=data.get("description"),
                     tags=data.get("tags"), thumbnail=thumbnail, publish_at=data.get("publish_at"))
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
    print(f"Video encoder: {ENCODER_NAMES[ENCODER]}")
    print("Open in browser: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
