"""
שכבת אינטגרציה מול Claude API.
המודול מבודד לגמרי את הפניות ל-AI כך שניתן יהיה להחליף ספק/מודל בעתיד
בלי לגעת בשאר האפליקציה - כל שאר הקוד קורא רק לפונקציות המוגדרות כאן.
"""
import json
import re
from typing import Any, Optional

from ..config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

_client = None


class ClaudeNotConfiguredError(Exception):
    pass


def _get_client():
    global _client
    if not ANTHROPIC_API_KEY:
        raise ClaudeNotConfiguredError(
            "לא הוגדר מפתח API של Anthropic. יש להוסיף ANTHROPIC_API_KEY לקובץ backend/.env"
        )
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


def _extract_json(text: str) -> Any:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    start = text.find("{")
    start_arr = text.find("[")
    if start == -1 or (0 <= start_arr < start):
        start = start_arr
    end = max(text.rfind("}"), text.rfind("]"))
    if start != -1 and end != -1:
        text = text[start:end + 1]
    return json.loads(text)


def _call(system: str, user_content: str, max_tokens: int = 2000) -> str:
    client = _get_client()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


ANALYZE_SYSTEM_PROMPT = """\
אתה עוזר AI במערכת "זיכרון ארגוני" שעוזרת לצוותים לצבור ידע עסקי לאורך זמן.
המשתמש הוסיף מקור מידע חדש (פגישה, מייל, מסמך וכו') תחת נושא עסקי מסוים.
המשימה שלך: לנתח את תוכן המקור ולהחזיר תשובה בפורמט JSON בלבד (ללא טקסט נוסף מחוץ ל-JSON), בעברית, עם השדות הבאים:

{
  "suggested_tags": ["תגית1", "תגית2", ...],           // 3-8 תגיות קצרות ורלוונטיות, בעברית
  "facts": ["..."],           // עובדות מפורשות שנאמרו/נכתבו במקור (לא פרשנות)
  "decisions": ["..."],       // החלטות שהתקבלו, אם צוינו
  "hypotheses": ["..."],      // השערות/הנחות שהועלו אך לא אושרו כעובדה
  "open_questions": ["..."],  // שאלות פתוחות שעדיין לא נענו
  "action_items": ["..."],    // משימות/מעקבים נדרשים
  "connections": [
    {"source_id": "<מזהה מקור מהרשימה שסופקה>", "description": "הסבר קצר על הקשר האפשרי בין המקור החדש למקור הקיים הזה"}
  ]
}

חשוב מאוד:
- אל תמציא מידע שלא מופיע בתוכן. אם קטגוריה מסוימת ריקה - החזר מערך ריק.
- "connections" - ציין רק חיבורים אמיתיים ומבוססים (למשל תגיות משותפות, נושא דומה, אזכור של אותו עניין), וסמן אותם כ"אפשריים" בתיאור - לא כעובדה מוכחת.
- החזר אך ורק JSON תקין, ללא טקסט לפני או אחרי.
"""


def analyze_source(
    topic_name: str,
    topic_description: str,
    source_title: str,
    source_type: str,
    source_date: str,
    content: str,
    existing_tags: list[str],
    candidate_sources: list[dict],
) -> dict:
    candidates_text = "\n".join(
        f"- id: {c['id']} | נושא: {c['topic_name']} | כותרת: {c['title']} | תאריך: {c['date']} | "
        f"תגיות: {', '.join(c['tags'])} | תקציר: {c['snippet']}"
        for c in candidate_sources
    ) or "(אין מקורות קיימים במערכת)"

    user_content = f"""\
נושא: {topic_name}
תיאור הנושא: {topic_description or '-'}
תגיות קיימות בנושא: {', '.join(existing_tags) or '-'}

המקור החדש שנוסף:
כותרת: {source_title}
סוג: {source_type}
תאריך: {source_date}
תוכן:
{content[:8000]}

רשימת מקורות קיימים במערכת (לצורך זיהוי קשרים אפשריים בלבד, כולל מקורות מנושאים אחרים):
{candidates_text}

נתח את המקור החדש והחזר JSON לפי הפורמט שהוגדר.
"""
    raw = _call(ANALYZE_SYSTEM_PROMPT, user_content, max_tokens=2500)
    return _extract_json(raw)


ASK_SYSTEM_PROMPT = """\
אתה עוזר AI במערכת "זיכרון ארגוני" (Organizational Memory) שמאפשרת לצוות לעקוב אחרי ידע עסקי שמצטבר
לאורך זמן מתוך פגישות, מיילים, מסמכים ועוד, המאורגנים בנושאים (Topics) עם ציר זמן.

תפקידך לענות בעברית על שאלת המשתמש לגבי נושא מסוים, תוך הסתמכות אך ורק על המקורות שסופקו לך כהקשר.

עליך להבחין בבירור בין הסוגים הבאים של מידע, ולהשתמש בכותרות ברורות בתשובה כאשר רלוונטי:
- **עובדות מפורשות** - דברים שנאמרו/נכתבו במפורש במקורות
- **החלטות** - החלטות שהתקבלו
- **השערות** - הנחות שהועלו אך לא אושרו
- **שאלות פתוחות** - מה שעדיין לא ידוע/לא נענה
- **הסקות AI** - מסקנות שאתה מסיק בעצמך מצירוף של מספר מקורות (סמן במפורש כ"הסקה שלי" ולא כעובדה)
- **קשרים אפשריים** - קשרים בין מקורות מאותו נושא או מנושאים אחרים (במיוחד דרך תגיות משותפות), תמיד מנוסחים כ"קשר אפשרי" ולא כקביעה ודאית

כל טענה מהותית שאתה כותב - ציין לצידה את המקור שעליו היא מבוססת (כותרת + תאריך).
אם המידע חסר או לא מספיק כדי לענות, אמור זאת בבירור במקום להמציא תשובה.
כתוב בעברית תקינה, בפורמט markdown קצר וברור (כותרות, בולטים).
"""


def ask_question(
    topic_name: str,
    topic_description: str,
    timeline_text: str,
    cross_topic_text: str,
    question: str,
) -> str:
    user_content = f"""\
נושא נוכחי: {topic_name}
תיאור: {topic_description or '-'}

ציר הזמן המלא של מקורות המידע בנושא זה (מהישן לחדש):
{timeline_text}

מקורות רלוונטיים אפשריים מנושאים אחרים (על בסיס תגיות משותפות):
{cross_topic_text or '(לא נמצאו מקורות רלוונטיים מנושאים אחרים)'}

שאלת המשתמש:
{question}
"""
    return _call(ASK_SYSTEM_PROMPT, user_content, max_tokens=3000)
