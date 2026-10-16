import { useEffect, useState } from "react";
import { api, formatMoment, SOURCE_TYPE_LABELS } from "../api";
import Modal from "./Modal";

// Earlier text versions of a source. Each is the state just before an edit; restoring one is an edit itself.
export default function VersionsModal({ source, canEdit, onClose, onRestored }) {
  const [versions, setVersions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listVersions(source.id).then(setVersions).catch((e) => setError(e.message));
  }, [source.id]);

  function open(id) {
    setSelected(id);
    setDetail(null);
    api.getVersion(source.id, id).then(setDetail).catch((e) => setError(e.message));
  }

  async function restore() {
    if (!confirm("לשחזר את הגרסה הזו? הגרסה הנוכחית תישמר בהיסטוריה.")) return;
    setBusy(true);
    try {
      await api.restoreVersion(source.id, selected);
      await onRestored();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  return (
    <Modal title={`גרסאות קודמות: ${source.title}`} onClose={onClose} wide>
      {versions.length === 0 && !error && <div className="muted">אין גרסאות קודמות.</div>}
      <ul className="versions-list">
        {versions.map((v, i) => (
          <li key={v.id}>
            <button type="button" className={`version-item ${selected === v.id ? "version-item-active" : ""}`} onClick={() => open(v.id)}>
              <strong>{v.title}</strong>
              <span className="muted">
                {" "}
                · הוחלפה ב-{formatMoment(v.replaced_at)}
                {v.replaced_by_name ? ` ע״י ${v.replaced_by_name}` : ""}
                {i === 0 ? " · הגרסה האחרונה לפני הנוכחית" : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {selected && !detail && !error && <div className="muted">טוען...</div>}
      {detail && (
        <div className="version-detail">
          <div className="muted">
            {SOURCE_TYPE_LABELS[detail.source_type] || detail.source_type} · {detail.date}
          </div>
          {detail.description && <p>{detail.description}</p>}
          <pre className="intake-preview version-content">{detail.content || "(ללא תוכן)"}</pre>
          {canEdit && (
            <button type="button" className="btn btn-primary" onClick={restore} disabled={busy}>
              שחזר גרסה זו
            </button>
          )}
        </div>
      )}
      {error && <div className="error-text">{error}</div>}
    </Modal>
  );
}
