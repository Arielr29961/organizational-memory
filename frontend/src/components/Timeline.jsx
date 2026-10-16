import SourceCard from "./SourceCard";

function matchesFilters(source, { query, mode, from, to }) {
  const q = query.trim().toLowerCase();
  if (q && !source.title.toLowerCase().includes(q)) return false;
  if (mode === "single") return !from || source.date === from;
  if (from && source.date < from) return false;
  if (to && source.date > to) return false;
  return true;
}

export default function Timeline({ sources, tagFilter, onClearFilter, onMutated, highlightId, filters, onFiltersChange, canEdit = true }) {
  const byTag = tagFilter ? sources.filter((s) => s.tags.some((t) => t.name === tagFilter)) : sources;
  const filtered = byTag.filter((s) => matchesFilters(s, filters));
  const sorted = [...filtered].sort((a, b) => (a.date < b.date ? 1 : -1));
  const dateFilterActive = filters.mode === "single" ? !!filters.from : !!(filters.from || filters.to);
  const searchActive = !!(filters.query.trim() || dateFilterActive);

  const update = (patch) => onFiltersChange({ ...filters, ...patch });

  return (
    <div className="timeline">
      <div className="timeline-filters">
        <input
          type="search"
          className="timeline-search"
          placeholder="חיפוש מקור לפי שם..."
          value={filters.query}
          onChange={(e) => update({ query: e.target.value })}
        />
        <select value={filters.mode} onChange={(e) => update({ mode: e.target.value, to: "" })}>
          <option value="range">טווח תאריכים</option>
          <option value="single">תאריך בודד</option>
        </select>
        <label>
          {filters.mode === "single" ? "תאריך" : "מתאריך"}
          <input type="date" value={filters.from} onChange={(e) => update({ from: e.target.value })} />
        </label>
        {filters.mode === "range" && (
          <label>
            עד תאריך
            <input type="date" value={filters.to} min={filters.from || undefined} onChange={(e) => update({ to: e.target.value })} />
          </label>
        )}
        {searchActive && (
          <button className="link-btn" onClick={() => onFiltersChange({ ...filters, query: "", from: "", to: "" })}>
            נקה חיפוש
          </button>
        )}
      </div>

      {tagFilter && (
        <div className="filter-banner">
          מציג מקורות עם התגית <strong>#{tagFilter}</strong>
          <button className="link-btn" onClick={onClearFilter}>
            נקה סינון
          </button>
        </div>
      )}
      {searchActive && (
        <div className="muted">
          מוצגים {sorted.length} מתוך {byTag.length} מקורות
        </div>
      )}
      {sorted.length === 0 && (
        <div className="muted">
          אין מקורות להצגה{tagFilter ? " עם תגית זו" : ""}
          {searchActive ? " שמתאימים לחיפוש" : ""}.
        </div>
      )}
      <div className="timeline-list">
        {sorted.map((source) => (
          <SourceCard key={source.id} source={source} onMutated={onMutated} highlighted={source.id === highlightId} canEdit={canEdit} />
        ))}
      </div>
    </div>
  );
}
