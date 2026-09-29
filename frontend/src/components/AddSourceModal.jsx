import { useState } from "react";
import { api, SOURCE_TYPES, INSIGHT_TYPE_LABELS } from "../api";
import Modal from "./Modal";

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

export default function AddSourceModal({ topicId, onClose, onCreated }) {
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState(SOURCE_TYPES[0].value);
  const [date, setDate] = useState(todayStr());
  const [content, setContent] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState([]);
  const [tagInput, setTagInput] = useState("");
  const [file, setFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [createdSourceId, setCreatedSourceId] = useState(null);

  function addTagFromInput() {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) setTags([...tags, t]);
    setTagInput("");
  }

  function handleTagKeyDown(e) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTagFromInput();
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title.trim() || (!content.trim() && !file)) {
      setError("יש להזין כותרת, ותוכן או קובץ מצורף");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("title", title.trim());
      fd.append("source_type", sourceType);
      fd.append("date", date);
      fd.append("content", content);
      fd.append("description", description);
      fd.append("tags", JSON.stringify(tags));
      if (file) fd.append("file", file);

      const source = await api.createSource(topicId, fd);
      setCreatedSourceId(source.id);
      setSaving(false);
      setAnalyzing(true);
      try {
        const result = await api.analyzeSource(source.id);
        setAnalysis(result);
      } catch (aiErr) {
        setError(`המקור נשמר בהצלחה, אך ניתוח ה-AI נכשל: ${aiErr.message}`);
      } finally {
        setAnalyzing(false);
      }
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  async function handleRemoveSuggestedTag(tagId) {
    try {
      await api.removeTag(createdSourceId, tagId);
      setAnalysis((a) => ({ ...a, suggested_tags: a.suggested_tags.filter((t) => t.id !== tagId) }));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleFinish() {
    await onCreated();
  }

  if (createdSourceId) {
    return (
      <Modal title="המקור נשמר — ניתוח AI" onClose={handleFinish} wide>
        {analyzing && <div className="muted">מריץ ניתוח AI על המקור (תגיות, עובדות, קשרים אפשריים)...</div>}
        {error && <div className="error-text">{error}</div>}
        {analysis && (
          <div className="analysis-result">
            {analysis.suggested_tags.length > 0 && (
              <section>
                <h4>תגיות שה-AI הציע</h4>
                <div className="tags-row">
                  {analysis.suggested_tags.map((t) => (
                    <span key={t.id} className="tag-chip tag-chip-ai">
                      #{t.name}
                      <button
                        type="button"
                        className="tag-remove"
                        title="הסר תגית"
                        onClick={() => handleRemoveSuggestedTag(t.id)}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              </section>
            )}

            {["fact", "decision", "hypothesis", "open_question", "action_item"].map((type) => {
              const items = analysis.insights.filter((i) => i.insight_type === type);
              if (items.length === 0) return null;
              return (
                <section key={type}>
                  <h4>{INSIGHT_TYPE_LABELS[type]}</h4>
                  <ul>
                    {items.map((i) => (
                      <li key={i.id}>{i.content}</li>
                    ))}
                  </ul>
                </section>
              );
            })}

            {analysis.connections.length > 0 && (
              <section>
                <h4>קשרים אפשריים למקורות אחרים</h4>
                <ul>
                  {analysis.connections.map((c) => (
                    <li key={c.id}>
                      <strong>
                        {c.related_title} ({c.related_topic_name})
                      </strong>
                      {c.shared_tags && <span className="muted"> — תגיות משותפות: {c.shared_tags}</span>}
                      <div>{c.description}</div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {analysis.suggested_tags.length === 0 &&
              analysis.insights.length === 0 &&
              analysis.connections.length === 0 && <div className="muted">ה-AI לא זיהה תובנות נוספות במקור זה.</div>}
          </div>
        )}
        <div className="form-actions">
          <button className="btn btn-primary" onClick={handleFinish} disabled={analyzing}>
            סגור
          </button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="הוספת מקור מידע" onClose={onClose} wide>
      <form onSubmit={handleSubmit} className="form">
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
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="לדוגמה: פגישה עם משפטית בנושא חדלות פירעון"
            required
          />
        </label>

        <label>
          תוכן (הדבקת טקסט)
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={6}
            placeholder="הדביקו כאן תמלול, טקסט מייל, סיכום וכו'..."
          />
        </label>

        <label>
          או צירוף קובץ (PDF, Word, Excel, CSV, טקסט)
          <input type="file" accept=".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md" onChange={(e) => setFile(e.target.files[0])} />
        </label>

        <label>
          תיאור קצר (אופציונלי)
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>

        <label>
          תגיות
          <div className="tag-input-box">
            {tags.map((t) => (
              <span key={t} className="tag-chip">
                #{t}
                <button type="button" className="tag-remove" onClick={() => setTags(tags.filter((x) => x !== t))}>
                  ×
                </button>
              </span>
            ))}
            <input
              type="text"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleTagKeyDown}
              onBlur={addTagFromInput}
              placeholder="הקלידו תגית ולחצו Enter"
            />
          </div>
        </label>

        {error && <div className="error-text">{error}</div>}

        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            ביטול
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "שומר..." : "שמור והרץ ניתוח AI"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
