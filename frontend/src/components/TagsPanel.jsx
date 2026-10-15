import { useEffect, useState } from "react";
import { api, SOURCE_TYPE_LABELS } from "../api";
import Modal from "./Modal";
import TagSynonyms from "./TagSynonyms";

export default function TagsPanel({ topicTags, onChanged }) {
  const [allTags, setAllTags] = useState([]);
  const [selectedTag, setSelectedTag] = useState(null);
  const [tagSources, setTagSources] = useState([]);
  const [loadingSources, setLoadingSources] = useState(false);
  const [cleanup, setCleanup] = useState({ duplicates: [], joined: [] });
  const [cleanupError, setCleanupError] = useState("");

  useEffect(() => {
    api.listTags().then(setAllTags);
    api.tagCleanup().then(setCleanup).catch((err) => setCleanupError(err.message));
  }, [topicTags]);

  async function runCleanup(action) {
    setCleanupError("");
    try {
      await action();
      await onChanged();
    } catch (err) {
      setCleanupError(err.message);
    }
  }

  function handleMerge(from, into) {
    if (!confirm(`למזג את #${from.name} לתוך #${into.name}? התגית #${from.name} תימחק וכל המקורות שלה יעברו לתגית #${into.name}.`)) return;
    runCleanup(() => api.mergeTag(from.id, into.id));
  }

  function handleSplit(tag) {
    if (!confirm(`לפצל את "${tag.name}" לתגיות נפרדות? התגית המשורשרת תימחק, וכל מקור שלה יקבל את התגיות הנפרדות.`)) return;
    runCleanup(() => api.splitTag(tag.id));
  }

  const relevantTags = allTags.filter((t) => topicTags.includes(t.name));

  async function openTag(tagName) {
    setSelectedTag(tagName);
    setLoadingSources(true);
    try {
      const sources = await api.sourcesByTag(tagName);
      setTagSources(sources);
    } finally {
      setLoadingSources(false);
    }
  }

  return (
    <div className="tags-panel">
      {relevantTags.length === 0 && <div className="muted">אין עדיין תגיות בנושא זה.</div>}
      <div className="tags-grid">
        {relevantTags.map((tag) => (
          <button key={tag.id} className="tag-card" onClick={() => openTag(tag.name)}>
            <div className="tag-card-name">#{tag.name}</div>
            <div className="tag-card-count">{tag.count} מקורות בכל המערכת</div>
          </button>
        ))}
      </div>

      {allTags.length > 0 && (
        <details className="tags-cleanup">
          <summary>
            ניקוי ומיזוג תגיות ({cleanup.duplicates.length} זוגות דומים, {cleanup.joined.length} תגיות משורשרות)
          </summary>
          <p className="muted">התגיות משותפות לכל הנושאים. מיזוג מעביר את כל המקורות לתגית שנשארת, ולא ניתן לביטול.</p>
          {cleanupError && <div className="error-text">{cleanupError}</div>}

          {cleanup.joined.length > 0 && (
            <section>
              <h4>תגיות שהן בעצם כמה תגיות ביחד</h4>
              {cleanup.joined.map((tag) => (
                <div key={tag.id} className="cleanup-row">
                  <span className="cleanup-names">
                    #{tag.name} <span className="muted">({tag.count})</span>
                  </span>
                  <button className="btn btn-sm" onClick={() => handleSplit(tag)}>
                    פצל לתגיות נפרדות
                  </button>
                </div>
              ))}
            </section>
          )}

          {cleanup.duplicates.length > 0 && (
            <section>
              <h4>תגיות שנראות דומות</h4>
              {cleanup.duplicates.map(({ a, b, score }) => (
                <div key={a.id + b.id} className="cleanup-row">
                  <span className="cleanup-names">
                    #{a.name} <span className="muted">({a.count})</span> ↔ #{b.name}{" "}
                    <span className="muted">({b.count})</span>
                    <span className="muted"> · דמיון {Math.round(score * 100)}%</span>
                  </span>
                  <span className="cleanup-actions">
                    <button className="btn btn-sm" onClick={() => handleMerge(b, a)}>
                      השאר #{a.name}
                    </button>
                    <button className="btn btn-sm" onClick={() => handleMerge(a, b)}>
                      השאר #{b.name}
                    </button>
                  </span>
                </div>
              ))}
            </section>
          )}
          <TagSynonyms onChanged={onChanged} />
        </details>
      )}

      {selectedTag && (
        <Modal title={`מקורות עם התגית #${selectedTag}`} onClose={() => setSelectedTag(null)} wide>
          {loadingSources && <div className="muted">טוען...</div>}
          {!loadingSources && tagSources.length === 0 && <div className="muted">לא נמצאו מקורות.</div>}
          <ul className="tag-sources-list">
            {tagSources.map((s) => (
              <li key={s.id}>
                <span className="type-badge">{SOURCE_TYPE_LABELS[s.source_type] || s.source_type}</span>
                <strong>{s.title}</strong>
                <span className="muted"> · {s.date} · נושא: {s.topic_name}</span>
                <div className="tag-source-preview">{(s.content || "").slice(0, 160)}</div>
              </li>
            ))}
          </ul>
        </Modal>
      )}
    </div>
  );
}
