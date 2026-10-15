import { useState } from "react";
import { api } from "../api";

function GroupCard({ group, busy, onMerge, onDismiss }) {
  const [keepId, setKeepId] = useState(group.keep_id);
  const [excluded, setExcluded] = useState(() => new Set());

  const mergeIds = group.tags.filter((t) => t.id !== keepId && !excluded.has(t.id)).map((t) => t.id);
  const keepName = group.tags.find((t) => t.id === keepId)?.name;

  function toggle(tagId) {
    setExcluded((prev) => {
      const next = new Set(prev);
      if (next.has(tagId)) next.delete(tagId);
      else next.add(tagId);
      return next;
    });
  }

  return (
    <div className="synonym-card">
      <div className="synonym-tags">
        {group.tags.map((t) => (
          <div key={t.id} className="synonym-tag">
            <label>
              <input type="radio" checked={keepId === t.id} onChange={() => setKeepId(t.id)} disabled={busy} /> השאר
            </label>
            <strong>#{t.name}</strong> <span className="muted">({t.count})</span>
            {keepId !== t.id && (
              <label className="muted">
                <input type="checkbox" checked={!excluded.has(t.id)} onChange={() => toggle(t.id)} disabled={busy} />{" "}
                מזג
              </label>
            )}
          </div>
        ))}
      </div>
      {group.reason && <div className="muted">{group.reason}</div>}
      <div className="synonym-actions">
        <button
          className="btn btn-sm btn-primary"
          disabled={busy || mergeIds.length === 0}
          onClick={() => onMerge(keepId, mergeIds)}
        >
          מזג {mergeIds.length} תגיות לתוך #{keepName}
        </button>
        <button className="btn btn-sm" disabled={busy} onClick={onDismiss}>
          התעלם
        </button>
      </div>
    </div>
  );
}

// Asks Claude for tags that could be merged. Nothing changes until the user approves a group.
export default function TagSynonyms({ onChanged }) {
  const [state, setState] = useState({ status: "idle", groups: [], checked: 0, error: "" });
  const [busy, setBusy] = useState(false);

  async function search() {
    setState({ status: "loading", groups: [], checked: 0, error: "" });
    try {
      const res = await api.suggestTagSynonyms();
      setState({ status: "done", groups: res.groups, checked: res.tags_checked, error: "" });
    } catch (err) {
      setState({ status: "error", groups: [], checked: 0, error: err.message });
    }
  }

  function groupKey(group) {
    return group.tags.map((t) => t.id).join("|");
  }

  function dismiss(group) {
    setState((s) => ({ ...s, groups: s.groups.filter((g) => groupKey(g) !== groupKey(group)) }));
  }

  async function merge(group, keepId, mergeIds) {
    const keepName = group.tags.find((t) => t.id === keepId)?.name;
    const names = group.tags.filter((t) => mergeIds.includes(t.id)).map((t) => `#${t.name}`).join(", ");
    if (!confirm(`למזג את ${names} לתוך #${keepName}? התגיות שימוזגו יימחקו וכל המקורות שלהן יעברו ל-#${keepName}. לא ניתן לבטל.`)) return;
    setBusy(true);
    try {
      await api.mergeTagGroup(keepId, mergeIds);
      // Drop the merged group, and remove the now-deleted tags from any other suggestion.
      setState((s) => ({
        ...s,
        groups: s.groups
          .filter((g) => groupKey(g) !== groupKey(group))
          .map((g) => ({ ...g, tags: g.tags.filter((t) => !mergeIds.includes(t.id)) }))
          .filter((g) => g.tags.length >= 2),
      }));
      await onChanged();
    } catch (err) {
      setState((s) => ({ ...s, error: err.message }));
    } finally {
      setBusy(false);
    }
  }

  const same = state.groups.filter((g) => g.kind === "same");
  const related = state.groups.filter((g) => g.kind !== "same");

  return (
    <section className="tag-synonyms">
      <h4>הצעות AI למיזוג תגיות</h4>
      <p className="muted">
        Claude מציע תגיות שאפשר למזג (נרדפות, וגם יחסי כלל ופרט). נשלחים אליו רק שמות תגיות וכותרות של עד שני מקורות
        לכל תגית. שום דבר לא משתנה בלי האישור שלך.
      </p>
      <button className="btn btn-sm btn-primary" onClick={search} disabled={state.status === "loading" || busy}>
        {state.status === "loading" ? "מחפש..." : "חפש הצעות בעזרת AI"}
      </button>
      {state.error && <div className="error-text">{state.error}</div>}

      {state.status === "done" && state.groups.length === 0 && (
        <div className="muted">ה-AI לא מצא תגיות למיזוג (נבדקו {state.checked} תגיות שנמצאות בשימוש).</div>
      )}

      {same.length > 0 && (
        <>
          <h5>אותו מושג (מומלץ למזג)</h5>
          {same.map((g) => (
            <GroupCard
              key={groupKey(g)}
              group={g}
              busy={busy}
              onMerge={(keepId, ids) => merge(g, keepId, ids)}
              onDismiss={() => dismiss(g)}
            />
          ))}
        </>
      )}
      {related.length > 0 && (
        <>
          <h5>קשורות או כלל ופרט (לשיקולך)</h5>
          {related.map((g) => (
            <GroupCard
              key={groupKey(g)}
              group={g}
              busy={busy}
              onMerge={(keepId, ids) => merge(g, keepId, ids)}
              onDismiss={() => dismiss(g)}
            />
          ))}
        </>
      )}
    </section>
  );
}
