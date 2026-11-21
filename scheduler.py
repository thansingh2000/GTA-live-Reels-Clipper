"""Daily publish slots: every upload gets the next free slot and YouTube publishes it at that time."""
import json
import os
import re
import threading
from datetime import datetime, time as dtime, timedelta, timezone
from zoneinfo import ZoneInfo

SCHEDULE_TZ = ZoneInfo("Asia/Kolkata")
# YouTube needs publishAt in the future; keep a margin for the upload itself.
MIN_LEAD = timedelta(minutes=20)
SEARCH_DAYS = 60
MAX_SLOTS = 12

DEFAULT_SLOTS = [
    {"time": "06:30", "label": "GTA 6 Gameplay", "keywords": "GTA 6, Gameplay"},
    {"time": "12:30", "label": "Funny Moments / Stunts", "keywords": "GTA 6, Funny Moments, Stunts"},
    {"time": "19:30", "label": "Police Chase / Secrets", "keywords": "GTA 6, Police Chase, Secrets"},
]


def clean_slots(slots):
    result = []
    for slot in slots or []:
        t = str(slot.get("time", "")).strip()
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            continue
        result.append({
            "time": t,
            "label": str(slot.get("label", "")).strip()[:60],
            "keywords": str(slot.get("keywords", "")).strip()[:200],
        })
    result.sort(key=lambda s: s["time"])
    return result[:MAX_SLOTS]


def to_key(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_key(key):
    return datetime.strptime(key, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def display(key):
    return from_key(key).astimezone(SCHEDULE_TZ).strftime("%a %d %b, %I:%M %p IST")


class Scheduler:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.booked = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.booked = json.load(fh)

    def _save(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        self.booked = {k: v for k, v in self.booked.items() if from_key(k) > cutoff}
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.booked, fh, indent=2)

    def free_slots(self, slots, count=6):
        now = datetime.now(SCHEDULE_TZ)
        found = []
        for day in range(SEARCH_DAYS):
            date = (now + timedelta(days=day)).date()
            for slot in slots:
                hh, mm = map(int, slot["time"].split(":"))
                dt = datetime.combine(date, dtime(hh, mm), SCHEDULE_TZ)
                key = to_key(dt)
                if dt > now + MIN_LEAD and key not in self.booked:
                    found.append({"key": key, "label": slot["label"], "keywords": slot["keywords"],
                                  "display": display(key)})
                    if len(found) >= count:
                        return found
        return found

    def slot_info(self, slots, key):
        local = from_key(key).astimezone(SCHEDULE_TZ).strftime("%H:%M")
        for slot in slots:
            if slot["time"] == local:
                return {"key": key, "label": slot["label"], "keywords": slot["keywords"], "display": display(key)}
        return {"key": key, "label": "", "keywords": "", "display": display(key)}

    def book(self, slots, owner, key=None):
        """Book `key` if it is a free future slot, otherwise the next free one. Returns the slot dict."""
        with self.lock:
            if key and key not in self.booked and from_key(key) > datetime.now(timezone.utc) + MIN_LEAD:
                slot = self.slot_info(slots, key)
            else:
                free = self.free_slots(slots, count=1)
                if not free:
                    return None
                slot = free[0]
            self.booked[slot["key"]] = {"owner": owner, "label": slot["label"]}
            self._save()
            return slot

    def release(self, key):
        with self.lock:
            if self.booked.pop(key, None) is not None:
                self._save()

    def upcoming(self, count=6):
        now = datetime.now(timezone.utc)
        keys = sorted(k for k in self.booked if from_key(k) > now)
        return [{"key": k, "label": self.booked[k].get("label", ""), "display": display(k)} for k in keys[:count]]
