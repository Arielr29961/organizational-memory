import { useCallback, useEffect, useRef, useState } from "react";
import { api, SOURCE_TYPES } from "../api";
import ParticipantsInput from "./ParticipantsInput";

const CONFIDENCE = { high: "גבוה", medium: "בינוני", low: "נמוך" };
const ACCEPT = ".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.eml";

// What the user changed in a row and has not saved yet; merged over the server's proposal.
function rowOf(item, draft = {}) {
  const base = {
    topicChoice: item.topic_id || (item.new_topic_name ? "__new__" : ""),
    newTopicName: item.new_topic_name || "",
    title: item.title,
    date: item.date || "",
    source_type: item.source_type,
    description: item.description,
    tags: item.tags,
    participants: item.participants,
  };
  return { ...base, ...draft };
}

function buildPatch(d) {
  const patch = { title: d.title, source_type: d.source_type, description: d.description, tags: d.tags, participants: d.participants };
  if (d.date) patch.date = d.date;
  if (d.topicChoice === "__new__") {
    if (d.newTopicName.trim()) patch.new_topic_name = d.newTopicName.trim();
    else patch.clear_topic = true;
  } else if (d.topicChoice) {
    patch.topic_id = d.topicChoice;
  } else {
    patch.clear_topic = true;
  }
  return patch;
}

export default function IntakeInbox({ onCountChange, onSourcesAdded }) {
  const [items, setItems] = useState([]);
  const [topics, setTopics] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [selected, setSelected] = useState(new Set());
  const [expanded, setExpanded] = useState(null);
  const [itemErrors, setItemErrors] = useState({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [newTag, setNewTag] = useState("");
  const fileInput = useRef(null);

  const load = useCallback(async () => {
    try {
      const list = await api.listIntake();
      setItems(list);
      onCountChange?.(list.length);
      return list;
    } catch (e) {
      setError(e.message);
      return [];
    }
  }, [onCountChange]);

  useEffect(() => {
    api
      .listIntake()
      .then((list) => {
        setItems(list);
        onCountChange?.(list.length);
      })
      .catch((e) => setError(e.message));
    api
      .listTopics()
      .then((all) => setTopics(all.filter((t) => t.role === "owner" || t.role === "editor")))
      .catch(() => setTopics([]));
  }, [onCountChange]);

  // Files are processed in the background: check again until none is still being read
  const processing = items.some((i) => i.status === "processing");
  useEffect(() => {
    if (!processing) return;
    const timer = setInterval(load, 2500);
    return () => clearInterval(timer);
  }, [processing, load]);

  const edit = (id, patch) => setDrafts((d) => ({ ...d, [id]: { ...d[id], ...patch } }));

  async function upload(fileList) {
    const files = [...fileList];
    if (files.length === 0) return;
    setUploading(true);
    setError("");
    setMessage("");
    try {
      const res = await api.uploadIntake(files);
      const skipped = res.skipped.map((s) => `${s.file_name}: ${s.reason}`);
      setMessage(`${res.created} קבצים נקלטו ומעובדים${skipped.length ? `. דולגו: ${skipped.join("; ")}` : ""}`);
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  }

  async function saveDrafts(ids) {
    for (const id of ids) {
      const item = items.find((i) => i.id === id);
      if (!item || !drafts[id] || item.status !== "pending") continue;
      await api.updateIntake(id, buildPatch(rowOf(item, drafts[id])));
    }
  }

  async function approve(ids) {
    if (ids.length === 0) return;
    setBusy(true);
    setError("");
    setMessage("");
    setItemErrors({});
    try {
      await saveDrafts(ids);
      const { results } = await api.approveIntake(ids);
      const failed = results.filter((r) => !r.ok);
      setItemErrors(Object.fromEntries(failed.map((r) => [r.id, r.error])));
      const okIds = new Set(results.filter((r) => r.ok).map((r) => r.id));
      setDrafts((d) => Object.fromEntries(Object.entries(d).filter(([id]) => !okIds.has(id))));
      setSelected((s) => new Set([...s].filter((id) => !okIds.has(id))));
      setMessage(`אושרו ${okIds.size} הצעות${failed.length ? `, ${failed.length} נכשלו (ראו את השגיאה בשורה)` : ""}`);
      await load();
      if (okIds.size) await onSourcesAdded?.();
    } catch (e) {
      setError(e.message);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function reject(ids) {
    if (ids.length === 0) return;
    if (!confirm(`לדחות ${ids.length} הצעות? הקבצים שהועלו יימחקו.`)) return;
    setBusy(true);
    try {
      await api.rejectIntake(ids);
      setSelected((s) => new Set([...s].filter((id) => !ids.includes(id))));
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function retry(id) {
    try {
      await api.retryIntake(id);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  const pending = items.filter((i) => i.status === "pending");
  const toggle = (id) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const selectedIds = [...selected].filter((id) => pending.some((i) => i.id === id));
  const highConfidence = pending.filter((i) => i.confidence === "high" && rowOf(i, drafts[i.id]).topicChoice).map((i) => i.id);

  function renderDetails(item, d) {
    return (
      <tr key={`${item.id}-details`} className="intake-details-row">
        <td colSpan={8}>
          <div className="intake-details">
            {item.reason && <p className="muted">למה הנושא הזה: {item.reason}</p>}
            {item.notes.map((n) => (
              <p key={n} className="muted">
                ⚠ {n}
              </p>
            ))}
            <label>
              תיאור
              <textarea rows={2} value={d.description} onChange={(e) => edit(item.id, { description: e.target.value })} />
            </label>
            <div className="field-block">
              <span>תגיות</span>
              <div className="tags-row">
                {d.tags.map((t) => (
                  <span key={t} className="tag-chip tag-chip-ai">
                    #{t}
                    <button type="button" className="tag-remove" onClick={() => edit(item.id, { tags: d.tags.filter((x) => x !== t) })}>
                      ×
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  className="intake-tag-input"
                  placeholder="+ תגית"
                  value={expanded === item.id ? newTag : ""}
                  onChange={(e) => setNewTag(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      const t = newTag.trim();
                      if (t && !d.tags.includes(t)) edit(item.id, { tags: [...d.tags, t] });
                      setNewTag("");
                    }
                  }}
                />
              </div>
            </div>
            <div className="field-block">
              <span>משתתפים / מכותבים</span>
              <ParticipantsInput
                participants={d.participants}
                onAdd={(p) => edit(item.id, { participants: [...d.participants, p] })}
                onRemove={(p) => edit(item.id, { participants: d.participants.filter((x) => x.email !== p.email) })}
              />
            </div>
            <div className="field-block">
              <span>
                תחילת התוכן ({item.content_length.toLocaleString()} תווים)
              </span>
              <pre className="intake-preview">{item.content_preview}</pre>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  function renderRow(item) {
    const d = rowOf(item, drafts[item.id]);
    if (item.status === "processing") {
      return (
        <tr key={item.id}>
          <td />
          <td>{item.file_name}</td>
          <td colSpan={5} className="muted">
            ⏳ ה-AI קורא את הקובץ...
          </td>
          <td />
        </tr>
      );
    }
    if (item.status === "error") {
      return (
        <tr key={item.id}>
          <td />
          <td>{item.file_name}</td>
          <td colSpan={5} className="error-text">
            {item.error}
          </td>
          <td className="intake-actions">
            <button type="button" className="btn btn-sm" onClick={() => retry(item.id)}>
              נסה שוב
            </button>
            <button type="button" className="btn btn-sm btn-danger" onClick={() => reject([item.id])}>
              הסר
            </button>
          </td>
        </tr>
      );
    }
    return [
      <tr key={item.id} className={itemErrors[item.id] ? "intake-row-error" : ""}>
        <td>
          <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggle(item.id)} />
        </td>
        <td title={item.file_name}>
          <div className="intake-file">{item.file_name}</div>
        </td>
        <td>
          <select value={d.topicChoice} onChange={(e) => edit(item.id, { topicChoice: e.target.value })}>
            <option value="">— בחרו נושא —</option>
            {topics.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
            <option value="__new__">➕ נושא חדש...</option>
          </select>
          {d.topicChoice === "__new__" && (
            <input
              type="text"
              placeholder="שם הנושא החדש"
              value={d.newTopicName}
              onChange={(e) => edit(item.id, { newTopicName: e.target.value })}
            />
          )}
        </td>
        <td>
          <input type="text" value={d.title} onChange={(e) => edit(item.id, { title: e.target.value })} />
        </td>
        <td>
          <input type="date" value={d.date} onChange={(e) => edit(item.id, { date: e.target.value })} />
        </td>
        <td>
          <select value={d.source_type} onChange={(e) => edit(item.id, { source_type: e.target.value })}>
            {SOURCE_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </td>
        <td>
          <span className={`confidence confidence-${item.confidence}`}>{CONFIDENCE[item.confidence]}</span>
        </td>
        <td className="intake-actions">
          <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={() => approve([item.id])}>
            אשר
          </button>
          <button type="button" className="btn btn-sm" onClick={() => setExpanded(expanded === item.id ? null : item.id)}>
            {expanded === item.id ? "סגור" : "פרטים"}
          </button>
          <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => reject([item.id])}>
            דחה
          </button>
        </td>
      </tr>,
      itemErrors[item.id] && (
        <tr key={`${item.id}-err`}>
          <td />
          <td colSpan={7} className="error-text">
            {itemErrors[item.id]}
          </td>
        </tr>
      ),
      expanded === item.id && renderDetails(item, d),
    ];
  }

  return (
    <div className="intake">
      <h2>תיבת הצעות</h2>
      <p className="muted">
        העלו קבצים (PDF, Word, Excel, CSV, טקסט, מייל .eml). ה-AI יציע לאיזה נושא כל קובץ שייך ויכין את פרטי המקור, ורק אחרי האישור שלכם ייווצר מקור.
        תוכן הקבצים נשלח ל-Anthropic לצורך הניתוח. עד 50 קבצים בהעלאה.
      </p>

      <div
        className={`intake-drop ${dragging ? "intake-drop-active" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          upload(e.dataTransfer.files);
        }}
      >
        <button type="button" className="btn btn-primary" disabled={uploading} onClick={() => fileInput.current?.click()}>
          {uploading ? "מעלה..." : "📥 בחירת קבצים"}
        </button>
        <span className="muted"> או גררו קבצים לכאן</span>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept={ACCEPT}
          hidden
          onChange={(e) => {
            upload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {message && <div className="intake-message">{message}</div>}
      {error && <div className="error-text">{error}</div>}

      {items.length === 0 ? (
        <div className="muted intake-empty">אין הצעות ממתינות.</div>
      ) : (
        <>
          <div className="intake-bulk">
            <label>
              <input
                type="checkbox"
                checked={pending.length > 0 && selectedIds.length === pending.length}
                onChange={(e) => setSelected(e.target.checked ? new Set(pending.map((i) => i.id)) : new Set())}
              />{" "}
              בחר הכל
            </label>
            <button type="button" className="btn btn-sm" onClick={() => setSelected(new Set(highConfidence))} disabled={highConfidence.length === 0}>
              בחר הצעות בביטחון גבוה ({highConfidence.length})
            </button>
            <button type="button" className="btn btn-sm btn-primary" disabled={busy || selectedIds.length === 0} onClick={() => approve(selectedIds)}>
              אשר נבחרים ({selectedIds.length})
            </button>
            <button type="button" className="btn btn-sm btn-danger" disabled={busy || selectedIds.length === 0} onClick={() => reject(selectedIds)}>
              דחה נבחרים
            </button>
          </div>

          <div className="intake-table-wrap">
            <table className="intake-table">
              <thead>
                <tr>
                  <th />
                  <th>קובץ</th>
                  <th>נושא</th>
                  <th>כותרת</th>
                  <th>תאריך</th>
                  <th>סוג</th>
                  <th>ביטחון</th>
                  <th />
                </tr>
              </thead>
              <tbody>{items.map(renderRow)}</tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
