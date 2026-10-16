import { ROLE_LABELS } from "../api";

export default function Sidebar({
  topics,
  selectedTopicId,
  onSelect,
  search,
  onSearchChange,
  onAddTopic,
  loading,
  error,
  user,
  onLogout,
  intakeCount = 0,
  intakeActive = false,
  onOpenIntake,
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

      <button className={`btn btn-block intake-nav ${intakeActive ? "intake-nav-active" : ""}`} onClick={onOpenIntake}>
        📥 תיבת הצעות{intakeCount > 0 && <span className="intake-badge">{intakeCount}</span>}
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
            {topic.role !== "owner" && (
              <div className="topic-item-shared">
                🤝 משותף ע״י {topic.owner_name} · {ROLE_LABELS[topic.role]}
              </div>
            )}
          </button>
        ))}
      </div>
      {user && (
        <div className="sidebar-user">
          <div className="sidebar-user-name" title={user.email}>
            {user.name}
          </div>
          <button type="button" className="link-btn" onClick={onLogout}>
            התנתקות
          </button>
        </div>
      )}
    </aside>
  );
}
