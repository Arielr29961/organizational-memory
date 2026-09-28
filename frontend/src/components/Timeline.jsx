import SourceCard from "./SourceCard";

export default function Timeline({ sources, tagFilter, onClearFilter, onMutated }) {
  const filtered = tagFilter ? sources.filter((s) => s.tags.some((t) => t.name === tagFilter)) : sources;
  const sorted = [...filtered].sort((a, b) => (a.date < b.date ? 1 : -1));

  return (
    <div className="timeline">
      {tagFilter && (
        <div className="filter-banner">
          מציג מקורות עם התגית <strong>#{tagFilter}</strong>
          <button className="link-btn" onClick={onClearFilter}>
            נקה סינון
          </button>
        </div>
      )}
      {sorted.length === 0 && <div className="muted">אין מקורות להצגה{tagFilter ? " עם תגית זו" : ""}.</div>}
      <div className="timeline-list">
        {sorted.map((source) => (
          <SourceCard key={source.id} source={source} onMutated={onMutated} />
        ))}
      </div>
    </div>
  );
}
