import { useState } from "react";
import { api, SOURCE_TYPE_LABELS } from "../api";

export default function SourceCard({ source, onMutated }) {
  const [expanded, setExpanded] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleAddTag(e) {
    e.preventDefault();
    if (!newTag.trim()) return;
    setBusy(true);
    try {
      await api.addTag(source.id, newTag.trim());
      setNewTag("");
      await onMutated();
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveTag(tagId) {
    setBusy(true);
    try {
      await api.removeTag(source.id, tagId);
      await onMutated();
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm(`למחוק את המקור "${source.title}"?`)) return;
    await api.deleteSource(source.id);
    await onMutated();
  }

  const preview = source.content && source.content.length > 260 ? source.content.slice(0, 260) + "…" : source.content;

  return (
    <div className="source-card">
      <div className="source-card-date">
        <div className="date-badge">{source.date}</div>
      </div>
      <div className="source-card-body">
        <div className="source-card-top">
          <span className="type-badge">{SOURCE_TYPE_LABELS[source.source_type] || source.source_type}</span>
          <h4>{source.title}</h4>
          <button className="btn-icon" onClick={handleDelete} title="מחיקת מקור">
            🗑
          </button>
        </div>
        {source.description && <p className="source-description">{source.description}</p>}
        {source.file_name && <div className="file-chip">📎 {source.file_name}</div>}

        <p className="source-content">
          {expanded ? source.content : preview}
          {source.content && source.content.length > 260 && (
            <button className="link-btn" onClick={() => setExpanded(!expanded)}>
              {expanded ? " הצג פחות" : " הצג עוד"}
            </button>
          )}
        </p>

        <div className="tags-row">
          {source.tags.map((tag) => (
            <span key={tag.id} className={`tag-chip ${tag.origin === "ai" ? "tag-chip-ai" : ""}`}>
              #{tag.name}
              {tag.origin === "ai" && <span className="ai-mark" title="תגית שהוצעה ע״י AI"> AI</span>}
              <button className="tag-remove" onClick={() => handleRemoveTag(tag.id)} disabled={busy}>
                ×
              </button>
            </span>
          ))}
          <form onSubmit={handleAddTag} className="inline-tag-form">
            <input
              type="text"
              placeholder="+ תגית"
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              disabled={busy}
            />
          </form>
        </div>
      </div>
    </div>
  );
}
