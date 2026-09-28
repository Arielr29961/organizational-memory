import { useEffect, useState } from "react";
import { api, SOURCE_TYPE_LABELS } from "../api";
import Modal from "./Modal";

export default function TagsPanel({ topicTags }) {
  const [allTags, setAllTags] = useState([]);
  const [selectedTag, setSelectedTag] = useState(null);
  const [tagSources, setTagSources] = useState([]);
  const [loadingSources, setLoadingSources] = useState(false);

  useEffect(() => {
    api.listTags().then(setAllTags);
  }, [topicTags]);

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
