import csv
import io
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
