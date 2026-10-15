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


def _call(system: str, user_content: str, max_tokens: int = 2000, history: Optional[list[dict]] = None) -> str:
    client = _get_client()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[*(history or []), {"role": "user", "content": user_content}],
    )
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


def _system_with_topic_context(base_prompt: str, topic_name: str, topic_description: Optional[str]) -> str:
    """Append the topic's user-written description to the system prompt as standing context."""
    description = (topic_description or "").strip()
    if not description:
        return base_prompt
    return f"""{base_prompt}
הקשר הנושא (הנחיית מערכת):
הנושא הנוכחי: {topic_name}
תיאור ומטרת הנושא, כפי שהוגדרו על ידי המשתמש: {description}

התחשב בתיאור זה בכל שלב: הבן ממנו מה חשוב ורלוונטי עסקית בנושא, תעדף לפיו מה לציין ומה לתייג, וכוון את התובנות והתשובות למטרה שהוגדרה.
התיאור הוא הקשר והנחיה בלבד - אל תציג אותו כעובדה שנאמרה במקורות, ואל תסיק ממנו מידע שאינו מופיע במקורות.
"""


ANALYZE_SYSTEM_PROMPT = """\
אתה עוזר AI במערכת "זיכרון ארגוני" שעוזרת לצוותים לצבור ידע עסקי לאורך זמן.
המשתמש הוסיף מקור מידע חדש (פגישה, מייל, מסמך וכו') תחת נושא עסקי מסוים.
המשימה שלך: לנתח את תוכן המקור ולהחזיר תשובה בפורמט JSON בלבד (ללא טקסט נוסף מחוץ ל-JSON), בעברית, עם השדות הבאים:

{
  "suggested_tags": ["תגית1", "תגית2", ...],           // 0-5 תגיות ספציפיות בעלות היגיון עסקי (ראה כללי תגיות)
  "facts": ["..."],           // עובדות מפורשות שנאמרו/נכתבו במקור (לא פרשנות)
  "decisions": ["..."],       // החלטות שהתקבלו, אם צוינו
  "hypotheses": ["..."],      // השערות/הנחות שהועלו אך לא אושרו כעובדה
  "open_questions": ["..."],  // שאלות פתוחות שעדיין לא נענו
  "action_items": ["..."],    // משימות/מעקבים נדרשים
  "connections": [
    {"source_id": "<מזהה מקור מהרשימה שסופקה>", "description": "הסבר קצר על הקשר האפשרי בין המקור החדש למקור הקיים הזה"}
  ]
}

כללי תגיות (חשוב מאוד):
מטרת תגית היא לקשר בין מקורות שונים כדי לגלות תובנות. תגית טובה היא ישות או עניין עסקי ספציפי שכדאי לעקוב אחריו לאורך זמן ובין נושאים:
שם פרויקט או יוזמה, לקוח או ספק, גוף או צוות ספציפי, מוצר או מערכת, החלטה או סוגיה עסקית מוגדרת, גורם סיכון מסוים, שם חוק או תקנה.
- אל תציע תגיות כלליות: שנים או תאריכים ("2024"), מילים רחבות ("תיקים", "חוב", "ביצועים", "נתונים", "ניהול", "בעיה", "שיפור"), ראשי תיבות כלליים ("KPI"), סוג המקור ("פגישה", "מייל", "מסמך") או שם הנושא עצמו.
- מבחן: האם יש היגיון עסקי לרכז יחד מקורות שונים לפי התגית הזו? אם כל מקור בנושא היה מקבל אותה, או אם היא לא מצמצמת כלום - אל תציע אותה.
- העדף תגית מפורטת וספציפית ("יתרת חוב גבוהה") על פני מילה בודדת כללית, אך שמור על אורך סביר (עד 4 מילים).
- אם קיימת ברשימת "תגיות קיימות במערכת" תגית שמתאימה בדיוק - השתמש בה בניסוח המדויק שלה ולא בניסוח חדש לאותו עניין.
- עדיף פחות תגיות. אם אין במקור שום דבר ספציפי שכדאי לתייג - החזר מערך ריק.

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
    known_tags: Optional[list[str]] = None,
) -> dict:
    candidates_text = "\n".join(
        f"- id: {c['id']} | נושא: {c['topic_name']} | כותרת: {c['title']} | תאריך: {c['date']} | "
        f"תגיות: {', '.join(c['tags'])} | תקציר: {c['snippet']}"
        for c in candidate_sources
    ) or "(אין מקורות קיימים במערכת)"

    user_content = f"""\
נושא: {topic_name}
תיאור הנושא: {topic_description or '-'}
תגיות שכבר קיימות במקור זה: {', '.join(existing_tags) or '-'}
תגיות קיימות במערכת (לשימוש חוזר בניסוח המדויק, אם מתאימות): {', '.join(known_tags or []) or '-'}

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
    system = _system_with_topic_context(ANALYZE_SYSTEM_PROMPT, topic_name, topic_description)
    raw = _call(system, user_content, max_tokens=2500)
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

ציטוט מקורות (חשוב מאוד): ליד כל מקור בהקשר מופיע מזהה בפורמט [id: ...].
כל טענה מהותית שאתה כותב - ציין מיד אחריה את המקור שעליו היא מבוססת, בפורמט [[המזהה]] (למשל: ... ירידה של 5% [[3f2a...]]). אם הטענה מבוססת על כמה מקורות, כתוב אותם זה אחר זה: [[מזהה1]] [[מזהה2]].
אל תכתוב בעצמך את הכותרת או התאריך של המקור - המערכת תציג אותם אוטומטית כקישור. השתמש רק במזהים המופיעים בהקשר שסופק, ואל תמציא מזהים.
קובץ שהמשתמש צירף להודעה אינו מקור שמור בנושא: אין לו מזהה, ואין לצטט אותו בפורמט [[...]]. כשאתה מסתמך עליו, ציין זאת בשמו ("בקובץ שצורף, <שם הקובץ>").
אם המידע חסר או לא מספיק כדי לענות, אמור זאת בבירור במקום להמציא תשובה.
כתוב בעברית תקינה, בפורמט markdown קצר וברור (כותרות, בולטים).
"""


def ask_question(
    topic_name: str,
    topic_description: str,
    timeline_text: str,
    cross_topic_text: str,
    question: str,
    history: Optional[list[dict]] = None,
    attachment_name: Optional[str] = None,
    attachment_text: Optional[str] = None,
) -> str:
    attachment_block = (
        f"\nקובץ שהמשתמש צירף להודעה זו ({attachment_name}):\n{attachment_text}\n" if attachment_text else ""
    )
    user_content = f"""\
נושא נוכחי: {topic_name}
תיאור: {topic_description or '-'}

ציר הזמן המלא של מקורות המידע בנושא זה (מהישן לחדש):
{timeline_text}

מקורות רלוונטיים אפשריים מנושאים אחרים (על בסיס תגיות משותפות):
{cross_topic_text or '(לא נמצאו מקורות רלוונטיים מנושאים אחרים)'}

{attachment_block}
שאלת המשתמש:
{question}
"""
    system = _system_with_topic_context(ASK_SYSTEM_PROMPT, topic_name, topic_description)
    return _call(system, user_content, max_tokens=3000, history=history)


TAG_GROUPS_SYSTEM_PROMPT = """\
אתה עוזר AI במערכת "זיכרון ארגוני". תפקידך לעזור למשתמש לנקות את אוצר התגיות: להציע אילו תגיות קיימות כדאי למזג.
הקלט: רשימת תגיות. לכל תגית: מזהה קצר, שם, מספר המקורות שמסומנים בה, וכותרות של עד שני מקורות כהקשר.

הצע קבוצות של תגיות שאפשר למזג, משני סוגים:
- "same" - אותו מושג בדיוק: נרדפות, קיצורים (למשל חדל"פ = חדלות פירעון), שגיאות כתיב, ריבוי/יחיד, הטיות, או ניסוח אחר לאותו עניין.
- "related" - יחס של כלל ופרט או חפיפה גדולה, שבו לפעמים המשתמש ירצה למזג (למשל "גבייה" ו"גבייה משפטית"). הצע רק כשמיזוג סביר באמת, ולא על תגיות שרק קשורות נושאית באופן רופף. המשתמש יחליט בעצמו, ולכן מותר להציע כאן גם מקרים גבוליים.

כללים:
- בכל קבוצה לפחות שתי תגיות. כל תגית מופיעה בקבוצה אחת לכל היותר; אם היא מתאימה לכמה, בחר את הקרובה ביותר.
- "keep" - מזהה התגית שהכי נכון להשאיר: ברורה, מלאה ונפוצה יותר.
- "reason" - משפט קצר בעברית שמסביר למה. הזכר בו את שמות התגיות ולא את המזהים (t1, t2...).
- בספק בין "same" ל-"related" - בחר "related". אם אין קשר ממשי - אל תציע כלל.
- אל תמציא מזהים; השתמש רק במזהים שניתנו.
- החזר JSON תקין בלבד, בפורמט:
{"groups": [{"kind": "same", "tag_ids": ["t1", "t2"], "keep": "t1", "reason": "..."}]}
"""


def suggest_tag_groups(tags: list[dict]) -> dict:
    """tags: [{'key': 't1', 'name', 'count', 'titles': [...]}]. Returns the model's raw JSON ({'groups': [...]})."""
    lines = "\n".join(
        f"- {t['key']} | {t['name']} | {t['count']} מקורות | כותרות: {'; '.join(t['titles']) or '-'}" for t in tags
    )
    raw = _call(TAG_GROUPS_SYSTEM_PROMPT, f"התגיות במערכת:\n{lines}\n\nהצע קבוצות למיזוג.", max_tokens=4000)
    return _extract_json(raw)
