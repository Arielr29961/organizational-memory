"""Tag normalization and similarity helpers (pure text logic, no AI and no external services)."""
import difflib
import re
import unicodedata

SEPARATORS_RE = re.compile(r"[,;،\n]+")
NIQQUD_RE = re.compile(r"[֑-ׇ]")  # Hebrew points and cantillation marks
NON_WORD_RE = re.compile(r"[\W_]+")


def clean_tag(name: str) -> str:
    """Display form: NFKC, no niqqud, no leading '#', unified Hebrew quotes, collapsed whitespace."""
    text = unicodedata.normalize("NFKC", name or "")
    text = NIQQUD_RE.sub("", text)
    text = text.replace("״", '"').replace("׳", "'").replace("“", '"').replace("”", '"').replace("’", "'")
    text = re.sub(r"\s+", " ", text).strip()
    return text.lstrip("#").strip()


def tag_key(name: str) -> str:
    """Matching key: two tags with the same key are the same tag (case, spaces, quotes and punctuation ignored)."""
    return NON_WORD_RE.sub("", clean_tag(name).lower())


def split_tag_input(raw: str) -> list[str]:
    """Split user/AI input such as 'a, b; c' into clean, de-duplicated tag names."""
    seen = set()
    names = []
    for part in SEPARATORS_RE.split(raw or ""):
        name = clean_tag(part)
        key = tag_key(name)
        if key and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def has_separator(name: str) -> bool:
    return len(split_tag_input(name)) > 1


def similarity(a: str, b: str) -> float:
    """0..1 similarity between two tag names; 1.0 means the same tag after normalization."""
    ka, kb = tag_key(a), tag_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka.isdigit() or kb.isdigit():  # years and numbers are not "similar" to each other
        return 0.0
    ratio = difflib.SequenceMatcher(None, ka, kb).ratio()
    shorter, longer = sorted((ka, kb), key=len)
    if len(shorter) >= 3 and shorter in longer and len(shorter) / len(longer) >= 0.5:
        # One tag mostly contains the other ("חוב גבוה" in "יתרת חוב גבוהה").
        ratio = max(ratio, 0.6 + 0.4 * len(shorter) / len(longer))
    if sorted(ka) == sorted(kb):
        # Same letters in a different order: a typing slip ("גכע" / "כגע").
        ratio = max(ratio, 0.85)
    return ratio


def find_similar(name: str, candidates: list[dict], threshold: float = 0.72, limit: int = 5) -> list[dict]:
    """candidates: [{'id', 'name', ...}]. Returns the most similar ones, best first, with a 'score'."""
    query_key = tag_key(name)
    scored = []
    for candidate in candidates:
        score = similarity(name, candidate["name"])
        if len(query_key) >= 3 and not query_key.isdigit() and tag_key(candidate["name"]).startswith(query_key):
            score = max(score, 0.78)  # the user may still be typing this tag ("חדלות" -> "חדלות פירעון")
        if score >= threshold:
            scored.append({**candidate, "score": round(score, 2)})
    scored.sort(key=lambda c: c["score"], reverse=True)
    return scored[:limit]


def find_duplicate_pairs(candidates: list[dict], threshold: float = 0.8) -> list[tuple[dict, dict, float]]:
    """Pairs of existing tags that are probably the same thing, best first."""
    pairs = []
    for i, a in enumerate(candidates):
        for b in candidates[i + 1 :]:
            score = similarity(a["name"], b["name"])
            if score >= threshold:
                pairs.append((a, b, round(score, 2)))
    pairs.sort(key=lambda p: p[2], reverse=True)
    return pairs


# Safety net behind the prompt rules: AI tags that are too generic to link sources meaningfully.
GENERIC_TAGS = {
    "חוב", "חובות", "תיקים", "תיק", "kpi", "נתונים", "מידע", "דוח", "דו\"ח", "דוחות", "ניהול", "בעיה", "בעיות",
    "שיפור", "ביצועים", "תהליך", "תהליכים", "עדכון", "סיכום", "ניתוח", "תוצאות", "נושא", "משימות", "החלטות",
    "פגישה", "פגישות", "מייל", "מסמך", "מצגת", "טבלה", "שנה", "חודש", "רבעון", "כללי", "אחר",
}
MAX_AI_TAGS = 5


def filter_ai_tags(tags: list, topic_name: str = "") -> list[str]:
    """Drop generic/low-value AI tags, dedupe, and cap the count."""
    seen = set()
    kept = []
    for raw in tags:
        if not isinstance(raw, str):
            continue
        t = raw.strip().lstrip("#").strip()
        key = t.lower()
        if (
            len(t) < 2
            or len(t) > 40
            or len(t.split()) > 4
            or key in seen
            or key in GENERIC_TAGS
            or key == topic_name.strip().lower()
            or re.fullmatch(r"[\d\s./\-_,:]+", t)  # numbers, years, dates
        ):
            continue
        seen.add(key)
        kept.append(t)
    return kept[:MAX_AI_TAGS]
