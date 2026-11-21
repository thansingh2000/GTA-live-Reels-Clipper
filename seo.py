"""Keyword-driven YouTube Shorts metadata (title, description, tags) — no external AI needed."""
import random
import re

TITLE_MAX = 100
DESCRIPTION_MAX = 4900
TAGS_MAX_CHARS = 470

GAME_TERMS = [
    (r"\bgta\s*(6|vi)\b", "GTA 6"),
    (r"\bgta\s*online\b", "GTA Online"),
    (r"\bgta\s*(5|v)\b", "GTA 5"),
    (r"\bgta\s*rp\b|\broleplay\b|\brp\b", "GTA RP"),
    (r"\bred\s*dead\b|\brdr\s*2\b", "Red Dead Redemption 2"),
    (r"\bgta\b|grand\s*theft\s*auto", "GTA"),
]
PLACE_TERMS = [
    (r"vice\s*city", "Vice City"),
    (r"los\s*santos", "Los Santos"),
    (r"liberty\s*city", "Liberty City"),
    (r"leonida", "Leonida"),
]
ACTION_TERMS = [
    (r"police|cops?\b|wanted", "Police Chase"),
    (r"heist|robbery|bank", "Heist"),
    (r"hyper\s*cars?|super\s*cars?", "Supercars"),
    (r"drift", "Drifting"),
    (r"stunts?", "Stunts"),
    (r"rac(e|ing)", "Racing"),
    (r"funny|fails?", "Funny Moments"),
    (r"missions?|story", "Missions"),
    (r"driver|driving", "Driving"),
    (r"chase", "Chase"),
]

HOOKS = [
    "{p} {s} Moment That Went CRAZY 🔥",
    "This {p} {s} Clip Is INSANE 😱",
    "Craziest {p} {s} Moment Ever 🤯",
    "Wait For The End... {p} {s} 😳",
    "Nobody Expected This In {p} {s} 💀",
    "Epic {p} {s} Highlight You Must Watch",
    "{p} {s} – Most Unbelievable Moment 😮",
    "I Can't Believe This Happened In {p} {s}",
    "{p} {s} Gameplay Moment Gone WILD 🚀",
    "Best {p} {s} Moment Of The Stream 🎮",
]


def _clean(text):
    text = re.sub(r"[^\w\s|\-:&']", " ", text or "", flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _first_match(terms, text):
    for pattern, label in terms:
        if re.search(pattern, text, re.IGNORECASE):
            return label
    return ""


def _hashtag(text):
    words = re.sub(r"[^\w\s]", "", text).split()
    return "#" + "".join(w[:1].upper() + w[1:] for w in words)


def _squash(text):
    return re.sub(r"\s+", " ", text).replace(" –  ", " – ").strip()


def extract_keywords(stream_title, focus_keywords=""):
    focus = [k.strip() for k in (focus_keywords or "").split(",") if k.strip()]
    cleaned = _clean(stream_title)
    game = _first_match(GAME_TERMS, cleaned)
    place = _first_match(PLACE_TERMS, cleaned)
    action = _first_match(ACTION_TERMS, cleaned)

    primary = focus[0] if focus else (game or "Gaming")
    secondary = focus[1] if len(focus) > 1 else (place or action)
    if secondary and secondary.lower() in primary.lower():
        secondary = action if action and action.lower() not in primary.lower() else ""
    extras = [k for k in focus[2:]] + [k for k in (game, place, action) if k]
    return primary, secondary, extras


def build_tags(primary, secondary, extras, base_tags=""):
    p = primary.lower()
    candidates = [
        primary, f"{p} shorts", f"{p} gameplay", f"{p} highlights", f"{p} live",
        f"{p} funny moments", f"{p} clips",
    ]
    if secondary:
        candidates += [secondary, f"{p} {secondary.lower()}"]
    candidates += extras
    candidates += [t.strip() for t in (base_tags or "").split(",") if t.strip()]
    candidates += ["gaming shorts", "gaming", "shorts", "viral gaming clips"]

    tags, seen, total = [], set(), 0
    for tag in candidates:
        tag = re.sub(r"[<>,]", "", tag).strip()
        key = tag.lower()
        if not tag or key in seen:
            continue
        cost = len(tag) + (2 if " " in tag else 0) + 1
        if total + cost > TAGS_MAX_CHARS:
            break
        seen.add(key)
        tags.append(tag)
        total += cost
    return ", ".join(tags)


def generate(clip_number, stream_title, channel="", focus_keywords="", base_tags="", variant=0):
    primary, secondary, extras = extract_keywords(stream_title, focus_keywords)
    rng = random.Random(clip_number * 7919 + variant * 104729)
    hook = HOOKS[rng.randrange(len(HOOKS))]

    core = _squash(hook.format(p=primary, s=secondary))
    title = core
    for suffix in (f" #Shorts {_hashtag(primary)}", " #Shorts"):
        if len(core) + len(suffix) <= TITLE_MAX:
            title = core + suffix
            break
    title = title[:TITLE_MAX]

    topic = _squash(f"{primary} {secondary}")
    action = (secondary or "gameplay").lower()
    hashtags = [_hashtag(primary), "#Shorts", "#Gaming"]
    if secondary:
        hashtags.insert(1, _hashtag(secondary))
    hashtags.append(_hashtag(primary) + "Shorts")

    keyword_line = ", ".join(dict.fromkeys(
        [topic, f"{primary} gameplay", f"{primary} shorts", f"{primary} highlights"] + extras
    ))
    lines = [
        core,
        "",
        f"{topic} highlight clipped straight from the live stream 🎮 "
        f"Watch this {primary} {action} moment till the end — it gets crazy!",
        "",
        f"🔔 Subscribe{' to ' + channel if channel else ''} for daily {primary} Shorts, "
        f"funny moments and epic gameplay highlights.",
        "👍 Like & comment what you want to see next!",
    ]
    if stream_title:
        lines += ["", f"📺 Clipped from live: {_clean(stream_title)}"]
    lines += ["", f"🔎 {keyword_line}", "", " ".join(dict.fromkeys(hashtags))]
    description = "\n".join(lines)[:DESCRIPTION_MAX]

    return {
        "title": title,
        "description": description,
        "tags": build_tags(primary, secondary, extras, base_tags),
    }
