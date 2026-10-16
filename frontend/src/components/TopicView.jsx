import { useEffect, useRef, useState } from "react";
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

const EMPTY_FILTERS = { query: "", mode: "range", from: "", to: "" };

export default function TopicView({ topicId, onTopicChanged, onTopicDeleted, focusSource, onOpenSource }) {
  const [topic, setTopic] = useState(null);
  const [sources, setSources] = useState([]);
  const [activeTab, setActiveTab] = useState("timeline");
  const [showAddSource, setShowAddSource] = useState(false);
  const [editingDescription, setEditingDescription] = useState(false);
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [tagFilter, setTagFilter] = useState(null);
  const [searchFilters, setSearchFilters] = useState(EMPTY_FILTERS);
  const [highlightId, setHighlightId] = useState(null);
  const handledFocus = useRef(null);
  // The open Ask-AI chat per topic, kept here so it survives tab and topic switches (undefined = not chosen yet).
  const [activeChats, setActiveChats] = useState({});

  // silent: refresh data in place without the full-screen loading state (keeps open panels and their state).
  async function loadAll({ silent = false } = {}) {
    if (!silent) setLoading(true);
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
    setSearchFilters(EMPTY_FILTERS);
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  // When a source link was clicked: show the timeline, scroll to that source's card and highlight it.
  useEffect(() => {
    if (!focusSource || loading || topic?.id !== focusSource.topicId || handledFocus.current === focusSource) return;
    handledFocus.current = focusSource;
    setActiveTab("timeline");
    setTagFilter(null);
    setSearchFilters(EMPTY_FILTERS); // the target card must not be hidden by a search or date filter
    // Wait a tick so the timeline tab has rendered the card.
    setTimeout(() => {
      document.getElementById(`source-${focusSource.sourceId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      setHighlightId(focusSource.sourceId);
    }, 100);
    setTimeout(() => setHighlightId(null), 3500);
  }, [focusSource, loading, topic]);

  async function handleSourceCreated() {
    setShowAddSource(false);
    await loadAll({ silent: true });
    await onTopicChanged();
  }

  async function handleSourceMutated() {
    await loadAll({ silent: true });
    await onTopicChanged();
  }

  async function saveDescription() {
    await api.updateTopic(topicId, { description: descriptionDraft });
    setEditingDescription(false);
    await loadAll({ silent: true });
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
            filters={searchFilters}
            onFiltersChange={setSearchFilters}
            onMutated={handleSourceMutated}
            highlightId={highlightId}
          />
        )}
        {activeTab === "tags" && <TagsPanel topicTags={topic.tags} onChanged={handleSourceMutated} />}
        {activeTab === "insights" && <InsightsPanel topicId={topicId} sources={sources} />}
        {activeTab === "ask" && (
          <AskAI
            topicId={topicId}
            onOpenSource={onOpenSource}
            activeChatId={activeChats[topicId]}
            onActiveChatChange={(chatId) => setActiveChats((m) => ({ ...m, [topicId]: chatId }))}
          />
        )}
      </div>

      {showAddSource && (
        <AddSourceModal topicId={topicId} onClose={() => setShowAddSource(false)} onCreated={handleSourceCreated} />
      )}
    </div>
  );
}
