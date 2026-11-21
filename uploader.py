import json
import os
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
QUOTA_REASONS = {"quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded", "rateLimitExceeded"}
# YouTube API quota resets at midnight Pacific time, so the daily limit follows the same day boundary.
QUOTA_TZ = ZoneInfo("America/Los_Angeles")
MAX_DAILY_LIMIT = 50
CONNECT_TIMEOUT = 120

DEFAULT_SETTINGS = {
    "youtube_enabled": False,
    "auto_upload": False,
    "require_review": True,
    "daily_limit": 5,
    "title_template": "GTA Live Highlight #{n} #Shorts",
    "description": "Clipped live from: {stream}\n\n#GTA #Gaming #Shorts",
    "tags": "GTA, GTA 6, Gaming, Shorts",
    "privacy": "private",
    "category_id": "20",
}


class YouTubeUploader:
    def __init__(self, base_dir, get_session_dir, get_stream_title, list_clips, log):
        self.client_secret = os.path.join(base_dir, "client_secret.json")
        self.token_path = os.path.join(base_dir, "token.json")
        self.settings_path = os.path.join(base_dir, "yt_settings.json")
        self.counts_path = os.path.join(base_dir, "upload_counts.json")
        self.daily_counts = {}
        if os.path.exists(self.counts_path):
            with open(self.counts_path, encoding="utf-8") as fh:
                self.daily_counts = json.load(fh)
        self.get_session_dir = get_session_dir
        self.get_stream_title = get_stream_title
        self.list_clips = list_clips
        self.log = log

        self.settings = dict(DEFAULT_SETTINGS)
        if os.path.exists(self.settings_path):
            with open(self.settings_path, encoding="utf-8") as fh:
                self.settings.update(json.load(fh))

        self.lock = threading.Lock()
        self.queue = deque()
        self.states = {}
        self.states_dir = None
        self.channel = ""
        self.connecting = False
        self.error = ""
        self.paused_reason = ""
        self.auto_enabled_at = time.time() if self.auto_active else None
        self._service = None

        if os.path.exists(self.token_path):
            self._try_load_channel()

        threading.Thread(target=self._watch_loop, daemon=True).start()
        threading.Thread(target=self._upload_loop, daemon=True).start()

    # ---------- auth ----------

    def _credentials(self):
        if not os.path.exists(self.token_path):
            return None
        creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(self.token_path, "w", encoding="utf-8") as fh:
                fh.write(creds.to_json())
        return creds if creds.valid else None

    def _youtube(self):
        creds = self._credentials()
        if not creds:
            raise RuntimeError("YouTube account is not connected.")
        if self._service is None:
            self._service = build("youtube", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _load_channel(self):
        resp = self._youtube().channels().list(part="snippet", mine=True).execute()
        items = resp.get("items") or []
        self.channel = items[0]["snippet"]["title"] if items else "(no channel on this account)"

    def _try_load_channel(self):
        try:
            self._load_channel()
            self.error = ""
            self.log(f"YouTube connected: {self.channel}")
        except HttpError as e:
            reason = ""
            try:
                reason = json.loads(e.content)["error"]["errors"][0]["reason"]
            except Exception:
                pass
            if reason == "accessNotConfigured":
                self.error = (
                    "Google login worked, but YouTube Data API v3 is not enabled in your Google Cloud project. "
                    "Enable it (APIs & Services → Library → YouTube Data API v3 → Enable); "
                    "the tool retries automatically every 30 seconds."
                )
            else:
                self.error = f"Google login worked, but reading your YouTube channel failed: {e.status_code} {reason or e.reason}"
        except Exception as e:
            self.error = f"Google login worked, but reading your YouTube channel failed: {e}"

    def connect(self):
        if not os.path.exists(self.client_secret):
            raise RuntimeError("client_secret.json not found in the project folder. See README → YouTube upload setup.")
        self.connect_attempt = getattr(self, "connect_attempt", 0) + 1
        attempt = self.connect_attempt
        self.connecting = True
        self.error = ""

        def run():
            try:
                flow = InstalledAppFlow.from_client_secrets_file(self.client_secret, SCOPES)
                # Google never redirects back when it blocks the login (e.g. account not a test user),
                # so the local callback server must give up on its own.
                creds = flow.run_local_server(port=0, open_browser=True, prompt="consent",
                                              timeout_seconds=CONNECT_TIMEOUT,
                                              success_message="YouTube connected. You can close this tab.")
                if attempt != self.connect_attempt:
                    return
                with open(self.token_path, "w", encoding="utf-8") as fh:
                    fh.write(creds.to_json())
                self._service = None
                self.paused_reason = ""
                self._try_load_channel()
            except Exception as e:
                if attempt == self.connect_attempt:
                    self.error = (
                        f"YouTube login did not finish ({e or 'timed out'}). If Google showed "
                        "'Access blocked', add your Gmail under Test users in Google Cloud and try again."
                    )
            finally:
                if attempt == self.connect_attempt:
                    self.connecting = False

        threading.Thread(target=run, daemon=True).start()

    def disconnect(self):
        if os.path.exists(self.token_path):
            os.remove(self.token_path)
        self._service = None
        self.channel = ""

    @property
    def connected(self):
        return bool(self.channel) and os.path.exists(self.token_path)

    # ---------- settings ----------

    @property
    def enabled(self):
        return bool(self.settings["youtube_enabled"])

    @property
    def auto_active(self):
        return self.enabled and bool(self.settings["auto_upload"])

    @property
    def daily_limit(self):
        return self.settings["daily_limit"]

    def update_settings(self, data):
        for key in DEFAULT_SETTINGS:
            if key in data:
                self.settings[key] = data[key]
        if self.settings["privacy"] not in ("private", "unlisted", "public"):
            self.settings["privacy"] = "private"
        try:
            limit = int(self.settings["daily_limit"])
        except (TypeError, ValueError):
            limit = DEFAULT_SETTINGS["daily_limit"]
        self.settings["daily_limit"] = max(1, min(MAX_DAILY_LIMIT, limit))
        if self.auto_active and self.auto_enabled_at is None:
            self.auto_enabled_at = time.time()
            self.paused_reason = ""
        elif not self.auto_active:
            self.auto_enabled_at = None
        with open(self.settings_path, "w", encoding="utf-8") as fh:
            json.dump(self.settings, fh, indent=2)

    # ---------- per-clip state ----------

    def _sync_states(self, session_dir):
        if session_dir == self.states_dir:
            return
        self.states_dir = session_dir
        self.states = {}
        self.queue.clear()
        path = os.path.join(session_dir, "uploads.json") if session_dir else None
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.states = json.load(fh)
            for name, st in self.states.items():
                if st.get("status") in ("queued", "uploading"):
                    st["status"] = "queued"
                    self.queue.append(name)

    def _save_states(self):
        if not self.states_dir:
            return
        with open(os.path.join(self.states_dir, "uploads.json"), "w", encoding="utf-8") as fh:
            json.dump(self.states, fh, indent=2)

    def clip_state(self, name):
        return self.states.get(name)

    def enqueue(self, name, title=None, description=None):
        with self.lock:
            self._sync_states(self.get_session_dir())
            st = self.states.get(name)
            if st and st.get("status") in ("queued", "uploading", "done"):
                return
            new_state = {"status": "queued"}
            if title is not None:
                new_state["title"] = self._clean_title(title, name)
            if description is not None:
                new_state["description"] = self._clean_description(description)
            self.states[name] = new_state
            self.queue.append(name)
            self.paused_reason = ""
            self._save_states()

    def _set_status(self, name, status):
        with self.lock:
            self._sync_states(self.get_session_dir())
            st = self.states.get(name)
            if st and st.get("status") in ("queued", "uploading", "done"):
                return
            self.states[name] = {"status": status}
            self._save_states()

    def mark_for_review(self, name):
        self._set_status(name, "review")

    def reject(self, name):
        self._set_status(name, "rejected")

    def _watch_loop(self):
        last_channel_retry = 0.0
        while True:
            time.sleep(3)
            if (not self.channel and not self.connecting and os.path.exists(self.token_path)
                    and time.time() - last_channel_retry > 30):
                last_channel_retry = time.time()
                self._try_load_channel()
            try:
                session_dir = self.get_session_dir()
                with self.lock:
                    self._sync_states(session_dir)
                if not (session_dir and self.auto_active and self.connected and self.auto_enabled_at):
                    continue
                for clip in self.list_clips(session_dir):
                    path = os.path.join(session_dir, clip["name"])
                    if clip["name"] not in self.states and os.path.getmtime(path) >= self.auto_enabled_at:
                        if self.settings["require_review"]:
                            self.mark_for_review(clip["name"])
                        else:
                            self.enqueue(clip["name"])
            except Exception as e:
                self.error = str(e)

    # ---------- uploading ----------

    @staticmethod
    def _clip_number(name):
        match = re.search(r"(\d+)\.\w+$", name)
        return int(match.group(1)) + 1 if match else 1

    def _clean_title(self, title, name):
        return re.sub(r"[<>]", "", title or "").strip()[:100] or f"Clip {self._clip_number(name)}"

    @staticmethod
    def _clean_description(description):
        return (description or "").replace("<", "").replace(">", "")[:4900]

    def default_metadata(self, name):
        values = defaultdict(str, n=self._clip_number(name), stream=self.get_stream_title() or "",
                             date=datetime.now().strftime("%d %b %Y"))
        return {
            "title": self._clean_title(self.settings["title_template"].format_map(values), name),
            "description": self._clean_description(self.settings["description"].format_map(values)),
        }

    def _metadata(self, name):
        defaults = self.default_metadata(name)
        st = self.states.get(name) or {}
        tags = [t.strip() for t in self.settings["tags"].split(",") if t.strip()]
        return {
            "snippet": {
                "title": st.get("title") or defaults["title"],
                "description": st.get("description", defaults["description"]),
                "tags": tags,
                "categoryId": str(self.settings["category_id"]),
            },
            "status": {
                "privacyStatus": self.settings["privacy"],
                "selfDeclaredMadeForKids": False,
            },
        }

    # ---------- daily limit ----------

    @staticmethod
    def _quota_day():
        return datetime.now(QUOTA_TZ).strftime("%Y-%m-%d")

    def uploads_today(self):
        return self.daily_counts.get(self._quota_day(), 0)

    def _count_upload(self):
        day = self._quota_day()
        self.daily_counts = {day: self.daily_counts.get(day, 0) + 1}
        with open(self.counts_path, "w", encoding="utf-8") as fh:
            json.dump(self.daily_counts, fh)

    @staticmethod
    def _next_reset_local():
        now = datetime.now(QUOTA_TZ)
        reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return reset.astimezone().strftime("%d %b, %I:%M %p")

    def limit_reason(self):
        if self.uploads_today() < self.daily_limit:
            return ""
        return (f"Daily limit reached ({self.uploads_today()}/{self.daily_limit} uploads). "
                f"Queued clips will upload automatically after the reset at {self._next_reset_local()}.")

    def _upload_loop(self):
        while True:
            time.sleep(1)
            if (not self.enabled or self.paused_reason or not self.queue
                    or not self.connected or self.limit_reason()):
                continue
            with self.lock:
                name = self.queue.popleft() if self.queue else None
                session_dir = self.states_dir
            if not name:
                continue
            st = self.states.setdefault(name, {})
            st.update(status="uploading", progress=0)
            try:
                video_id = self._upload_file(os.path.join(session_dir, name), self._metadata(name), st)
                self._count_upload()
                st.update(status="done", video_id=video_id, url=f"https://youtube.com/shorts/{video_id}")
                st.pop("error", None)
                self.log(f"Uploaded {name} → https://youtube.com/shorts/{video_id}")
            except HttpError as e:
                reason = ""
                try:
                    reason = json.loads(e.content)["error"]["errors"][0]["reason"]
                except Exception:
                    pass
                if reason in QUOTA_REASONS:
                    st.update(status="queued")
                    with self.lock:
                        self.queue.appendleft(name)
                    self.paused_reason = (
                        "YouTube API daily upload quota reached. Uploads are paused; "
                        "queued clips will resume when you press Retry (quota resets daily)."
                    )
                    self.log(f"Upload paused: {reason}")
                else:
                    self._count_upload()
                    st.update(status="error", error=f"{e.status_code}: {reason or e.reason}")
                    self.log(f"Upload failed for {name}: {st['error']}")
            except Exception as e:
                st.update(status="error", error=str(e))
                self.log(f"Upload failed for {name}: {e}")
            with self.lock:
                if session_dir == self.states_dir:
                    self._save_states()

    def _upload_file(self, path, body, st):
        media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
        request = self._youtube().videos().insert(part="snippet,status", body=body, media_body=media)
        response, failures = None, 0
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    st["progress"] = int(status.progress() * 100)
                failures = 0
            except HttpError as e:
                if e.status_code in (500, 502, 503, 504) and failures < 5:
                    failures += 1
                    time.sleep(2 ** failures)
                    continue
                raise
            except (ConnectionError, TimeoutError, OSError):
                if failures >= 5:
                    raise
                failures += 1
                time.sleep(2 ** failures)
        return response["id"]

    def resume(self):
        self.paused_reason = ""

    def status(self):
        return {
            "has_client_secret": os.path.exists(self.client_secret),
            "connected": self.connected,
            "channel": self.channel,
            "connecting": self.connecting,
            "error": self.error,
            "paused": self.paused_reason or self.limit_reason(),
            "queue": len(self.queue),
            "uploads_today": self.uploads_today(),
            "daily_limit": self.daily_limit,
            "max_daily_limit": MAX_DAILY_LIMIT,
            "settings": self.settings,
        }
