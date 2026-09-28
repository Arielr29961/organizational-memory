import { useEffect, useState } from "react";
import { api, INSIGHT_TYPE_LABELS } from "../api";

const TYPE_ORDER = ["decision", "fact", "open_question", "hypothesis", "action_item"];

export default function InsightsPanel({ topicId, sources }) {
  const [insights, setInsights] = useState([]);
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const [i, c] = await Promise.all([api.topicInsights(topicId), api.topicConnections(topicId)]);
      setInsights(i);
      setConnections(c);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  if (loading) return <div className="muted">טוען תובנות...</div>;

  if (sources.length === 0) {
    return <div className="muted">הוסיפו מקורות לנושא כדי לראות כאן תובנות AI.</div>;
  }

  if (insights.length === 0 && connections.length === 0) {
    return (
      <div className="muted">
        עדיין אין תובנות AI שמורות. תובנות נוצרות אוטומטית בעת הוספת מקור חדש (ניתוח ה-AI רץ בשמירה).
      </div>
    );
  }

  return (
    <div className="insights-panel">
      {TYPE_ORDER.map((type) => {
        const items = insights.filter((i) => i.insight_type === type);
        if (items.length === 0) return null;
        return (
          <section key={type} className="insight-section">
            <h3>{INSIGHT_TYPE_LABELS[type]}</h3>
            <ul>
              {items.map((i) => (
                <li key={i.id}>
                  <span>{i.content}</span>
                  <span className="insight-source-ref">
                    — {i.source_title} ({i.source_date})
                  </span>
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      {connections.length > 0 && (
        <section className="insight-section">
          <h3>קשרים אפשריים (כולל מנושאים אחרים)</h3>
          <ul>
            {connections.map((c) => (
              <li key={c.id}>
                <strong>{c.source_title}</strong> ↔ <strong>{c.related_title}</strong>
                {c.related_topic_name && <span className="muted"> (נושא: {c.related_topic_name})</span>}
                {c.shared_tags && <div className="muted">תגיות משותפות: {c.shared_tags}</div>}
                <div>{c.description}</div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
