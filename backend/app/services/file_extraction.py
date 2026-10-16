import csv
import io
import re
from datetime import date as date_type
from html.parser import HTMLParser
from pathlib import Path


def extract_text(file_path: Path, original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()

    try:
        if suffix == ".pdf":
            return _extract_pdf(file_path)
        if suffix == ".docx":
            return _extract_docx(file_path)
        if suffix in (".xlsx", ".xlsm"):
            return _extract_xlsx(file_path)
        if suffix == ".csv":
            return _extract_csv(file_path)
        if suffix in (".txt", ".md"):
            return file_path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".eml":
            return eml_to_text(parse_eml(file_path))
    except Exception as exc:
        return f"[שגיאה בחילוץ טקסט אוטומטי מהקובץ: {exc}]"

    return "[לא ניתן לחלץ טקסט אוטומטית מסוג קובץ זה. ניתן להוסיף תוכן ידנית.]"


def _extract_pdf(file_path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    parts = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"--- עמוד {i + 1} ---\n{text.strip()}")
    return "\n\n".join(parts)


def _extract_docx(file_path: Path) -> str:
    import docx

    doc = docx.Document(str(file_path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_xlsx(file_path: Path) -> str:
    import openpyxl

    wb = openpyxl.load_workbook(str(file_path), data_only=True)
    parts = []
    for sheet in wb.worksheets:
        parts.append(f"--- גיליון: {sheet.title} ---")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(cells):
                parts.append("\t".join(cells))
    return "\n".join(parts)


def _extract_csv(file_path: Path) -> str:
    parts = []
    with open(file_path, "r", encoding="utf-8-sig", errors="ignore", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            parts.append("\t".join(row))
    return "\n".join(parts)


class _HtmlText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    text = "".join(parser.parts)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def parse_eml(file_path: Path) -> dict:
    """Headers and body of an .eml file: {subject, date, from, to, cc, body, attachments}; people are (name, email) pairs."""
    from email import policy
    from email.parser import BytesParser
    from email.utils import getaddresses, parsedate_to_datetime

    with open(file_path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    def people(header: str) -> list[tuple[str, str]]:
        return [(str(name or "").strip(), str(addr or "").strip()) for name, addr in getaddresses([str(v) for v in msg.get_all(header, [])]) if addr]

    sent = None
    try:
        sent = parsedate_to_datetime(str(msg["date"])).date() if msg["date"] else None
    except (TypeError, ValueError):
        sent = None

    body = ""
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is not None:
        content = part.get_content()
        body = _html_to_text(content) if part.get_content_type() == "text/html" else str(content).strip()

    return {
        "subject": str(msg["subject"] or "").strip(),
        "date": sent if isinstance(sent, date_type) else None,
        "from": people("from"),
        "to": people("to"),
        "cc": people("cc"),
        "body": body,
        "attachments": [a.get_filename() or "(ללא שם)" for a in msg.iter_attachments()],
    }


def _format_people(pairs: list[tuple[str, str]]) -> str:
    return ", ".join(f"{name} <{addr}>" if name else addr for name, addr in pairs)


def eml_to_text(mail: dict) -> str:
    lines = []
    if mail["from"]:
        lines.append(f"מאת: {_format_people(mail['from'])}")
    if mail["to"]:
        lines.append(f"אל: {_format_people(mail['to'])}")
    if mail["cc"]:
        lines.append(f"עותק: {_format_people(mail['cc'])}")
    if mail["date"]:
        lines.append(f"תאריך: {mail['date']}")
    lines.append(f"נושא: {mail['subject']}")
    if mail["attachments"]:
        lines.append("קבצים מצורפים (לא נקראו): " + ", ".join(mail["attachments"]))
    return "\n".join(lines) + "\n\n" + mail["body"]
