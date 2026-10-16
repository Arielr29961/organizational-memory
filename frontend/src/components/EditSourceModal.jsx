import { useState } from "react";
import { api, SOURCE_TYPES } from "../api";
import Modal from "./Modal";

// Edits the text of a source. Every saved change keeps the previous text as a version (see VersionsModal).
export default function EditSourceModal({ source, onClose, onSaved }) {
  const [title, setTitle] = useState(source.title);
  const [sourceType, setSourceType] = useState(source.source_type);
  const [date, setDate] = useState(source.date);
  const [description, setDescription] = useState(source.description);
  const [content, setContent] = useState(source.content);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const changed =
    title.trim() !== source.title ||
    sourceType !== source.source_type ||
    date !== source.date ||
    description !== source.description ||
    content !== source.content;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim()) return setError("יש להזין כותרת");
    if (!date) return setError("יש להזין תאריך");
    setSaving(true);
    setError("");
    try {
      await api.updateSource(source.id, { title, source_type: sourceType, date, description, content });
      await onSaved();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <Modal title="עריכת מקור" onClose={onClose} wide>
      <form className="form" onSubmit={handleSubmit}>
        <div className="form-row">
          <label>
            סוג מקור
            <select value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
              {SOURCE_TYPES.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            תאריך
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
          </label>
        </div>
        <label>
          כותרת
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} required />
        </label>
        <label>
          תיאור קצר
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label>
          תוכן
          <textarea rows={14} value={content} onChange={(e) => setContent(e.target.value)} />
        </label>
        <p className="muted">הגרסה הנוכחית תישמר בהיסטוריית הגרסאות. תגיות ומשתתפים נערכים ישירות בכרטיס המקור.</p>
        {error && <div className="error-text">{error}</div>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            ביטול
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving || !changed}>
            {saving ? "שומר..." : "שמירה"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
