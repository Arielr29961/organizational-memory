import { useEffect, useState } from "react";
import { api } from "../api";
import Timeline from "./Timeline";
import TagsPanel from "./TagsPanel";
import InsightsPanel from "./InsightsPanel";
import AskAI from "./AskAI";
import AddSourceModal from "./AddSourceModal";

const TABS = [
  { key: "timeline", label: "ציר זמן ומקורות" },
  { key: "tags", label: "תגיות" },
  { key: "insights", label: "תובנות AI" },
  { key: "ask", label: "שאל את ה-AI" },
];

export default function TopicView({ topicId, onTopicChanged, onTopicDeleted }) {
  const [topic, setTopic] = useState(null);
  const [sources, setSources] = useState([]);
  const [activeTab, setActiveTab] = useState("timeline");
  const [showAddSource, setShowAddSource] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [tagFilter, setTagFilter] = useState(null);

  async function loadAll() {
    setLoading(true);
    try {
      const [t, s] = await Promise.all([api.getTopic(topicId), api.listSources(topicId)]);
      setTopic(t);
      setSources(s);
      setDescriptionDraft(t.description || "");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setActiveTab("timeline");
    setTagFilter(null);
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  async function handleSourceCreated() {
    setShowAddSource(false);
    await loadAll();
    await onTopicChanged();
  }

  async function handleSourceMutated() {
    await loadAll();
    await onTopicChanged();
  }

  async function saveDescription() {
    await api.updateTopic(topicId, { description: descriptionDraft });
    setEditingDescription(false);
    await loadAll();
    await onTopicChanged();
  }

  async function handleDeleteTopic() {
    if (!confirm(`למחוק את הנושא "${topic.name}" וכל המקורות שבו? פעולה זו אינה הפיכה.`)) return;
    await api.deleteTopic(topicId);
    await onTopicDeleted(topicId);
  }

  if (loading || !topic) {
    return <div className="loading-state">טוען נושא...</div>;
  }

  return (
    <div className="topic-view">
      <header className="topic-header">
        <div className="topic-header-top">
          <div>
            <h2>{topic.name}</h2>
            {editingDescription ? (
              <div className="description-edit">
                <textarea
                  value={descriptionDraft}
                  onChange={(e) => setDescriptionDraft(e.target.value)}
                  rows={2}
                />
                <div className="form-actions">
                  <button className="btn btn-sm" onClick={() => setEditingDescription(false)}>
                    ביטול
                  </button>
                  <button className="btn btn-sm btn-primary" onClick={saveDescription}>
                    שמור
                  </button>
                </div>
              </div>
            ) : (
              <p className="topic-description" onClick={() => setEditingDescription(true)} title="לחצו לעריכה">
                {topic.description || "אין תיאור. לחצו כדי להוסיף."}
              </p>
            )}
          </div>
          <div className="topic-header-actions">
            <button className="btn btn-primary" onClick={() => setShowAddSource(true)}>
              + הוספת מקור
            </button>
            <button className="btn btn-danger" onClick={handleDeleteTopic}>
              מחיקת נושא
            </button>
          </div>
        </div>

        <div className="topic-tags-row">
          {topic.tags.length === 0 && <span className="muted">אין עדיין תגיות בנושא זה</span>}
          {topic.tags.map((tag) => (
            <button
              key={tag}
              className={`tag-chip ${tagFilter === tag ? "tag-chip-active" : ""}`}
              onClick={() => {
                setActiveTab("timeline");
                setTagFilter(tagFilter === tag ? null : tag);
              }}
            >
              #{tag}
            </button>
          ))}
        </div>
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab-btn ${activeTab === tab.key ? "active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="tab-content">
        {activeTab === "timeline" && (
          <Timeline
            sources={sources}
            tagFilter={tagFilter}
            onClearFilter={() => setTagFilter(null)}
            onMutated={handleSourceMutated}
          />
        )}
        {activeTab === "tags" && <TagsPanel topicTags={topic.tags} />}
        {activeTab === "insights" && <InsightsPanel topicId={topicId} sources={sources} />}
        {activeTab === "ask" && <AskAI topicId={topicId} />}
      </div>

      {showAddSource && (
        <AddSourceModal topicId={topicId} onClose={() => setShowAddSource(false)} onCreated={handleSourceCreated} />
      )}
    </div>
  );
}
