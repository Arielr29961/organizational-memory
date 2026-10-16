import { useState } from "react";
import { api, canOpenInBrowser, formatMoment, openSourceFile, SOURCE_TYPE_LABELS } from "../api";
import EditSourceModal from "./EditSourceModal";
import VersionsModal from "./VersionsModal";
import ParticipantsInput from "./ParticipantsInput";
import TagSuggest from "./TagSuggest";

export default function SourceCard({ source, onMutated, highlighted, canEdit = true }) {
  const [expanded, setExpanded] = useState(false);
  const [newTag, setNewTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showVersions, setShowVersions] = useState(false);
  const [fileError, setFileError] = useState("");

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

  async function addTagByName(name) {
    setBusy(true);
    try {
      await api.addTag(source.id, name);
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

  async function handleFile(open) {
    setFileError("");
    try {
      await openSourceFile(source, { open });
    } catch (err) {
      setFileError(err.message);
    }
  }

  const preview = source.content && source.content.length > 260 ? source.content.slice(0, 260) + "…" : source.content;

  return (
    <div id={`source-${source.id}`} className={`source-card ${highlighted ? "source-card-highlight" : ""}`}>
      <div className="source-card-date">
        <div className="date-badge">{source.date}</div>
      </div>
      <div className="source-card-body">
        <div className="source-card-top">
          <span className="type-badge">{SOURCE_TYPE_LABELS[source.source_type] || source.source_type}</span>
          <h4>{source.title}</h4>
          {canEdit && (
            <button className="btn-icon" onClick={() => setEditing(true)} title="עריכת מקור">
              ✏️
            </button>
          )}
          {canEdit && (
            <button className="btn-icon" onClick={handleDelete} title="מחיקת מקור">
              🗑
            </button>
          )}
        </div>
        {source.edited_at && (
          <div className="edited-note">
            ✏️ נערך ב-{formatMoment(source.edited_at)}
            {source.edited_by_name ? ` ע״י ${source.edited_by_name}` : ""}
            {source.version_count > 0 && (
              <button type="button" className="link-btn" onClick={() => setShowVersions(true)}>
                {" "}
                גרסאות קודמות ({source.version_count})
              </button>
            )}
          </div>
        )}
        {source.description && <p className="source-description">{source.description}</p>}
        {source.has_file && (
          <div className="file-chip">
            📎 {source.file_name}
            {canOpenInBrowser(source.file_name) && (
              <button type="button" className="link-btn" onClick={() => handleFile(true)}>
                {" "}
                פתיחה
              </button>
            )}
            <button type="button" className="link-btn" onClick={() => handleFile(false)}>
              {" "}
              הורדה
            </button>
          </div>
        )}
        {fileError && <div className="error-text">{fileError}</div>}

        <p className="source-content">
          {expanded ? source.content : preview}
          {source.content && source.content.length > 260 && (
            <button className="link-btn" onClick={() => setExpanded(!expanded)}>
              {expanded ? " הצג פחות" : " הצג עוד"}
            </button>
          )}
        </p>

        <details className="participants-details" open={source.participants.length > 0 || undefined}>
          <summary>
            👥 משתתפים{source.participants.length > 0 ? ` (${source.participants.length})` : ""}
          </summary>
          <ParticipantsInput
            participants={source.participants}
            readOnly={!canEdit}
            onAdd={async (p) => {
              await api.addParticipant(source.id, p);
              await onMutated();
            }}
            onRemove={async (p) => {
              await api.removeParticipant(source.id, p.id);
              await onMutated();
            }}
            onRename={async (p, name) => {
              await api.renamePerson(p.id, name);
              await onMutated();
            }}
          />
        </details>

        <div className="tags-row">
          {source.tags.map((tag) => (
            <span key={tag.id} className={`tag-chip ${tag.origin === "ai" ? "tag-chip-ai" : ""}`}>
              #{tag.name}
              {tag.origin === "ai" && <span className="ai-mark" title="תגית שהוצעה ע״י AI"> AI</span>}
              {canEdit && (
                <button className="tag-remove" onClick={() => handleRemoveTag(tag.id)} disabled={busy}>
                  ×
                </button>
              )}
            </span>
          ))}
          {canEdit && (
            <form onSubmit={handleAddTag} className="inline-tag-form">
              <input
                type="text"
                placeholder="+ תגית"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                disabled={busy}
              />
            </form>
          )}
        </div>
        {canEdit && <TagSuggest text={newTag} exclude={source.tags.map((t) => t.name)} onPick={addTagByName} />}
      </div>
      {editing && (
        <EditSourceModal
          source={source}
          onClose={() => setEditing(false)}
          onSaved={async () => {
            setEditing(false);
            await onMutated();
          }}
        />
      )}
      {showVersions && (
        <VersionsModal
          source={source}
          canEdit={canEdit}
          onClose={() => setShowVersions(false)}
          onRestored={async () => {
            setShowVersions(false);
            await onMutated();
          }}
        />
      )}
    </div>
  );
}
