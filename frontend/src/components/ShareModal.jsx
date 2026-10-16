import { useEffect, useState } from "react";
import { api, getStoredUser, ROLE_LABELS } from "../api";
import Modal from "./Modal";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Who the topic is shared with. The owner manages the list; everyone else sees it and may leave.
export default function ShareModal({ topic, onClose, onLeft }) {
  const me = getStoredUser();
  const isOwner = topic.role === "owner";
  const [members, setMembers] = useState([]);
  const [people, setPeople] = useState([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listMembers(topic.id).then(setMembers).catch((e) => setError(e.message));
    if (isOwner) api.listPeople().then(setPeople).catch(() => setPeople([]));
  }, [topic.id, isOwner]);

  const typed = email.trim().toLowerCase();
  const knownPerson = people.find((p) => p.email === typed);
  const validEmail = EMAIL_RE.test(typed);

  async function run(action) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const handleAdd = (e) => {
    e.preventDefault();
    if (!validEmail) return setError("יש להזין כתובת מייל תקינה");
    if (!knownPerson && !name.trim()) return setError("מייל חדש בספר האנשים, יש להזין גם את השם המלא");
    run(async () => {
      setMembers(await api.addMember(topic.id, { email: typed, name: knownPerson ? undefined : name.trim(), role }));
      setEmail("");
      setName("");
      api.listPeople().then(setPeople).catch(() => {});
    });
  };

  const handleRole = (m, newRole) => run(async () => setMembers(await api.updateMember(topic.id, m.person_id, newRole)));

  const handleRemove = (m) => {
    if (!confirm(`להסיר את ${m.name} מהנושא?`)) return;
    run(async () => setMembers(await api.removeMember(topic.id, m.person_id)));
  };

  const handleLeave = () => {
    if (!confirm(`לעזוב את הנושא "${topic.name}"? הנושא יוסר מהרשימה שלך.`)) return;
    run(async () => {
      await api.removeMember(topic.id, me.id);
      await onLeft();
    });
  };

  const candidates = people.filter((p) => !members.some((m) => m.email === p.email));

  return (
    <Modal title={`שיתוף הנושא: ${topic.name}`} onClose={onClose} wide>
      <div className="share-members">
        {members.map((m) => (
          <div key={m.person_id} className="share-row">
            <div className="share-person">
              <strong>{m.name}</strong>
              <span className="muted" dir="ltr">
                {m.email}
              </span>
              {!m.registered && <span className="muted">(עדיין לא נרשם)</span>}
            </div>
            {isOwner && m.role !== "owner" ? (
              <>
                <select value={m.role} onChange={(e) => handleRole(m, e.target.value)} disabled={busy}>
                  <option value="viewer">{ROLE_LABELS.viewer}</option>
                  <option value="editor">{ROLE_LABELS.editor}</option>
                </select>
                <button type="button" className="btn btn-sm btn-danger" onClick={() => handleRemove(m)} disabled={busy}>
                  הסרה
                </button>
              </>
            ) : (
              <span className="type-badge">{ROLE_LABELS[m.role]}</span>
            )}
          </div>
        ))}
      </div>

      {isOwner && (
        <form className="form share-add" onSubmit={handleAdd}>
          <h4>הוספת אדם</h4>
          <div className="participant-add">
            <input
              type="email"
              dir="ltr"
              placeholder="מייל"
              list="share-people"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                setError("");
              }}
              disabled={busy}
            />
            <datalist id="share-people">
              {candidates.map((p) => (
                <option key={p.id} value={p.email}>
                  {p.name}
                </option>
              ))}
            </datalist>
            {validEmail && !knownPerson && (
              <input type="text" placeholder="שם מלא (מייל חדש)" value={name} onChange={(e) => setName(e.target.value)} disabled={busy} />
            )}
            {knownPerson && <span className="muted">{knownPerson.name}</span>}
            <select value={role} onChange={(e) => setRole(e.target.value)} disabled={busy}>
              <option value="viewer">{ROLE_LABELS.viewer}: קורא ושואל את ה-AI</option>
              <option value="editor">{ROLE_LABELS.editor}: גם מוסיף ועורך מקורות</option>
            </select>
            <button type="submit" className="btn btn-primary" disabled={busy || !validEmail}>
              + שיתוף
            </button>
          </div>
          <p className="muted">מי שעוד לא נרשם יראה את הנושא ברגע שייכנס עם המייל הזה.</p>
        </form>
      )}

      {error && <div className="error-text">{error}</div>}

      <div className="form-actions">
        {!isOwner && (
          <button type="button" className="btn btn-danger" onClick={handleLeave} disabled={busy}>
            עזיבת הנושא
          </button>
        )}
        <button type="button" className="btn" onClick={onClose}>
          סגור
        </button>
      </div>
    </Modal>
  );
}
