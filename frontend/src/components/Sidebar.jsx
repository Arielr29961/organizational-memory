export default function Sidebar({
  topics,
  selectedTopicId,
  onSelect,
  search,
  onSearchChange,
  onAddTopic,
  loading,
  error,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1>זיכרון ארגוני</h1>
        <p className="sidebar-subtitle">Organizational Memory POC</p>
      </div>

      <button className="btn btn-primary btn-block" onClick={onAddTopic}>
        + הוספת נושא
      </button>

      <input
        type="text"
        className="search-input"
        placeholder="חיפוש נושא..."
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
      />

      <div className="topics-list">
        {loading && <div className="muted">טוען נושאים...</div>}
        {error && <div className="error-text">{error}</div>}
        {!loading && topics.length === 0 && <div className="muted">אין עדיין נושאים. צרו נושא ראשון!</div>}
        {topics.map((topic) => (
          <button
            key={topic.id}
            className={`topic-item ${selectedTopicId === topic.id ? "active" : ""}`}
            onClick={() => onSelect(topic.id)}
          >
            <div className="topic-item-name">{topic.name}</div>
            <div className="topic-item-meta">
              {topic.source_count} מקורות
              {topic.tags.length > 0 && ` · ${topic.tags.slice(0, 3).join(", ")}`}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
