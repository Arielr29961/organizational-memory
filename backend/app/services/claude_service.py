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


def _call_with_stop(system: str, user_content: str, max_tokens: int = 2000, history: Optional[list[dict]] = None) -> tuple[str, Optional[str]]:
    """(visible text, stop reason). The model thinks before it answers and those tokens count against max_tokens, so a
    small limit can cut the visible answer off ('max_tokens')."""
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
    return "".join(parts), getattr(response, "stop_reason", None)


def _call(system: str, user_content: str, max_tokens: int = 2000, history: Optional[list[dict]] = None) -> str:
    return _call_with_stop(system, user_content, max_tokens, history)[0]


def _call_json(system: str, user_content: str, max_tokens: int = 4000) -> Any:
    """Ask for a JSON answer. A malformed or cut-off answer is retried once (with a bigger limit if it was cut off)."""
    truncated = False
    for _attempt in range(2):
        raw, stop = _call_with_stop(system, user_content, max_tokens)
        truncated = stop == "max_tokens"
        try:
            return _extract_json(raw)
        except json.JSONDecodeError:
            if truncated:
                max_tokens *= 2
    raise ValueError("תשובת ה-AI נחתכה לפני שהסתיימה, נסו שוב" if truncated else "תשובת ה-AI לא הייתה בפורמט תקין, נסו שוב")


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
המשימה שלך: להציע תגיות למקור. החזר תשובה בפורמט JSON בלבד (ללא טקסט נוסף מחוץ ל-JSON), בעברית:

{"suggested_tags": ["תגית1", "תגית2"]}   // 0-5 תגיות ספציפיות בעלות היגיון עסקי (ראה כללי תגיות)

כללי תגיות (חשוב מאוד):
מטרת תגית היא לקשר בין מקורות שונים כדי לגלות תובנות. תגית טובה היא ישות או עניין עסקי ספציפי שכדאי לעקוב אחריו לאורך זמן ובין נושאים:
שם פרויקט או יוזמה, לקוח או ספק, גוף או צוות ספציפי, מוצר או מערכת, החלטה או סוגיה עסקית מוגדרת, גורם סיכון מסוים, שם חוק או תקנה.
- אל תציע תגיות כלליות: שנים או תאריכים ("2024"), מילים רחבות ("תיקים", "חוב", "ביצועים", "נתונים", "ניהול", "בעיה", "שיפור"), ראשי תיבות כלליים ("KPI"), סוג המקור ("פגישה", "מייל", "מסמך") או שם הנושא עצמו.
- מבחן: האם יש היגיון עסקי לרכז יחד מקורות שונים לפי התגית הזו? אם כל מקור בנושא היה מקבל אותה, או אם היא לא מצמצמת כלום - אל תציע אותה.
- העדף תגית מפורטת וספציפית ("יתרת חוב גבוהה") על פני מילה בודדת כללית, אך שמור על אורך סביר (עד 4 מילים).
- אם קיימת ברשימת "תגיות קיימות במערכת" תגית שמתאימה בדיוק - השתמש בה בניסוח המדויק שלה ולא בניסוח חדש לאותו עניין.
- עדיף פחות תגיות. אם אין במקור שום דבר ספציפי שכדאי לתייג - החזר מערך ריק.
- אל תמציא מידע שלא מופיע בתוכן. החזר אך ורק JSON תקין, ללא טקסט לפני או אחרי.
"""


def analyze_source(
    topic_name: str,
    topic_description: str,
    source_title: str,
    source_type: str,
    source_date: str,
    content: str,
    existing_tags: list[str],
    known_tags: Optional[list[str]] = None,
    participants: Optional[list[str]] = None,
) -> dict:
    user_content = f"""\
נושא: {topic_name}
תיאור הנושא: {topic_description or '-'}
תגיות שכבר קיימות במקור זה: {', '.join(existing_tags) or '-'}
תגיות קיימות במערכת (לשימוש חוזר בניסוח המדויק, אם מתאימות): {', '.join(known_tags or []) or '-'}

המקור החדש שנוסף:
כותרת: {source_title}
סוג: {source_type}
תאריך: {source_date}
משתתפים/מכותבים: {', '.join(participants or []) or '-'}
תוכן:
{content[:8000]}

הצע תגיות והחזר JSON לפי הפורמט שהוגדר.
"""
    system = _system_with_topic_context(ANALYZE_SYSTEM_PROMPT, topic_name, topic_description)
    return _call_json(system, user_content, max_tokens=2000)


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
    focus_tag: Optional[str] = None,
) -> str:
    attachment_block = (
        f"\nקובץ שהמשתמש צירף להודעה זו ({attachment_name}):\n{attachment_text}\n" if attachment_text else ""
    )
    if focus_tag:
        focus_block = (
            f"המשתמש מתמקד בתגית #{focus_tag}. כל המקורות שלהלן, בנושא זה ובנושאים אחרים, הם רק מקורות שמסומנים בתגית הזו. "
            "ענה על בסיסם בלבד, והזכר בקצרה שהתשובה מתמקדת בתגית.\n\n"
        )
        timeline_title = f"מקורות המידע בנושא זה שמסומנים בתגית #{focus_tag} (מהישן לחדש)"
        cross_title = f"מקורות מנושאים אחרים שמסומנים באותה תגית (#{focus_tag})"
    else:
        focus_block = ""
        timeline_title = "ציר הזמן המלא של מקורות המידע בנושא זה (מהישן לחדש)"
        cross_title = "מקורות מנושאים אחרים שנבחרו כרלוונטיים לשאלה"
    user_content = f"""\
נושא נוכחי: {topic_name}
תיאור: {topic_description or '-'}

{focus_block}{timeline_title}:
{timeline_text}

{cross_title}:
{cross_topic_text or '(לא נמצאו מקורות רלוונטיים מנושאים אחרים)'}

{attachment_block}
שאלת המשתמש:
{question}
"""
    system = _system_with_topic_context(ASK_SYSTEM_PROMPT, topic_name, topic_description)
    return _call(system, user_content, max_tokens=6000, history=history)


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
    return _call_json(TAG_GROUPS_SYSTEM_PROMPT, f"התגיות במערכת:\n{lines}\n\nהצע קבוצות למיזוג.", max_tokens=6000)


SELECT_SOURCES_SYSTEM_PROMPT = """\
אתה עוזר AI במערכת "זיכרון ארגוני". המשתמש שואל שאלה בהקשר נושא מסוים. קיבלת רשימה קצרה של מקורות מנושאים אחרים.
בחר מתוכה את המקורות שעשויים לעזור לענות על השאלה: מידע רקע, נתונים קשורים, החלטות קודמות או הקשר עסקי רלוונטי.
אין צורך בתגית משותפת: החלט לפי המשמעות של השאלה ושל המקור. אם מצוין שמקור חולק תגיות עם הנושא, זה רמז בלבד.

כללים:
- בחר רק מקורות שרלוונטיים באמת לשאלה (עד 8), מהחשוב ביותר לפחות חשוב. אם אין כאלה - החזר רשימה ריקה.
- אל תמציא מזהים; השתמש רק במזהים שניתנו.
- החזר JSON תקין בלבד: {"source_ids": ["s1", "s2"]}
"""


def select_related_sources(
    topic_name: str, topic_description: Optional[str], questions: list[str], index: list[dict]
) -> dict:
    """index: [{'key', 'source', 'tags', 'shared_tags'}]. Returns the model's raw JSON ({'source_ids': [...]})."""
    lines = "\n".join(
        f"- {e['key']} | נושא: {e['source'].topic.name} | {e['source'].date} | {e['source'].title} | "
        f"תגיות: {', '.join(e['tags']) or '-'}"
        + (f" | חולק תגיות עם הנושא: {', '.join(e['shared_tags'])}" if e["shared_tags"] else "")
        + (f" | משתתפים: {', '.join(sp.person.name for sp in e['source'].participants)}" if e["source"].participants else "")
        + f" | תקציר: {(e['source'].content or '')[:200].replace(chr(10), ' ')}"
        for e in index
    )
    asked = "\n".join(f"- {q}" for q in questions)
    user_content = f"""\
הנושא הנוכחי: {topic_name}
תיאור הנושא: {topic_description or '-'}

שאלת המשתמש (והשאלות הקודמות בשיחה, מהישנה לחדשה):
{asked}

מקורות מנושאים אחרים:
{lines}

בחר את המקורות הרלוונטיים והחזר JSON.
"""
    return _call_json(SELECT_SOURCES_SYSTEM_PROMPT, user_content, max_tokens=2000)


INTAKE_SYSTEM_PROMPT = """\
אתה עוזר AI במערכת "זיכרון ארגוני". המשתמש ייבא קובץ (מסמך, מייל, תמלול, טבלה וכו') והמשימה שלך להכין הצעה למקור מידע חדש:
לאיזה נושא קיים הוא שייך, ומה פרטי המקור. המשתמש יבדוק ויאשר, ולכן עדיף להיות זהיר וכן לגבי רמת הביטחון.
החזר JSON בלבד, בפורמט:

{"topic": "t3" או null,
 "new_topic_name": "שם קצר לנושא חדש" או null,
 "confidence": "high" | "medium" | "low",
 "reason": "משפט אחד: למה זה הנושא שנבחר (או למה אף נושא לא מתאים)",
 "title": "כותרת קצרה וברורה למקור",
 "date": "YYYY-MM-DD" או null,
 "source_type": "meeting_transcript" | "meeting_summary" | "email" | "presentation" | "spreadsheet" | "document" | "other",
 "description": "תיאור של משפט או שניים",
 "tags": ["תגית"],
 "participants": [{"name": "שם", "email": "כתובת"}]}

כללים:
- topic: רק אחד המפתחות מהרשימה שסופקה (t1, t2...), או null. בחר נושא רק כשהתוכן מתאים בבירור לשם, לתיאור או למקורות הקודמים שלו.
- אם אף נושא לא מתאים: topic = null, והצע ב-new_topic_name שם קצר לנושא חדש. אם גם זה לא ברור, החזר שניהם null.
- confidence: "high" רק כשההתאמה לנושא חד-משמעית; "medium" כשסביר אך לא בטוח; "low" כשיש ספק או שאין נושא.
- title: בשפת המסמך, עד 80 תווים. אל תעתיק את שם הקובץ אם יש כותרת טובה יותר בתוכן.
- date: תאריך הפגישה / המייל / המסמך כפי שמופיע בתוכן. אם אינו מופיע בבירור: null. אל תנחש.
- source_type: תמלול מילולי של פגישה = meeting_transcript; סיכום או פרוטוקול = meeting_summary; מייל = email; מצגת = presentation; טבלה או נתונים = spreadsheet; מסמך כתוב = document; אחר = other.
- tags: 0-5 תגיות ספציפיות בעלות היגיון עסקי (פרויקט, לקוח, ספק, צוות, מערכת, סוגיה מוגדרת). לא כלליות ("חוב", "ניהול", "פגישה", שנים). אם תגית קיימת ברשימה מתאימה, השתמש בניסוח המדויק שלה.
- participants: רק אנשים שכתובת המייל שלהם מופיעה בפועל בטקסט. אל תמציא כתובות ואל תנחש. אם אין, מערך ריק.
- אל תמציא מידע שלא מופיע בתוכן. החזר אך ורק JSON תקין.
"""


def propose_intake(
    file_name: str,
    text: str,
    topics: list[dict],
    known_tags: list[str],
    today: str,
    mail_headers: Optional[str] = None,
) -> dict:
    """topics: [{'key', 'name', 'description', 'recent_titles', 'top_tags'}]. Returns the model's raw JSON proposal."""
    topic_lines = "\n".join(
        f"- {t['key']} | {t['name']} | תיאור: {t['description'] or '-'} | מקורות אחרונים: "
        f"{'; '.join(t['recent_titles']) or '-'} | תגיות נפוצות: {', '.join(t['top_tags']) or '-'}"
        for t in topics
    ) or "(אין עדיין נושאים)"
    user_content = f"""\
היום: {today}
שם הקובץ: {file_name}
{('כותרות המייל (נקראו אוטומטית): ' + mail_headers) if mail_headers else ''}

הנושאים הקיימים של המשתמש:
{topic_lines}

תגיות קיימות במערכת (לשימוש חוזר בניסוח המדויק, אם מתאימות): {', '.join(known_tags) or '-'}

תוכן הקובץ (תחילתו):
{text[:12000]}

הכן את ההצעה והחזר JSON.
"""
    return _call_json(INTAKE_SYSTEM_PROMPT, user_content, max_tokens=4000)
