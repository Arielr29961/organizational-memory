import { useEffect, useState } from "react";
import { api, getStoredUser } from "../api";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

// Participants / recipients of a source. Every person is a real e-mail address plus the full name stored for it in
// the address book; a known address fills its name by itself, a new one needs the name once.
// onRename(person, newName) is optional: when given, saved people (those with an id) get an edit button; the new
// name applies everywhere the address is used, because the name lives in the address book.
// onAdd({ email, name }) and onRemove(person) may be async; a thrown error is shown under the field.
export default function ParticipantsInput({ participants, onAdd, onRemove, onRename, disabled, readOnly = false }) {
  const [people, setPeople] = useState([]);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");

  // The address book is fetched when the user starts typing, so cards that are never edited cost no request
  const [loaded, setLoaded] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  useEffect(() => {
    if (!loaded) return;
    api.listPeople().then(setPeople).catch(() => setPeople([]));
  }, [loaded, reloadKey]);

  const typed = email.trim().toLowerCase();
  const known = people.find((p) => p.email === typed);
  const validEmail = EMAIL_RE.test(typed);
  const alreadyIn = (e) => participants.some((p) => p.email === e);
  const query = typed;
  const suggestions =
    query.length < 1 || known
      ? []
      : people
          .filter((p) => !alreadyIn(p.email) && (p.email.includes(query) || p.name.toLowerCase().includes(query)))
          .slice(0, 5);

  async function add(person) {
    setBusy(true);
    setError("");
    try {
      await onAdd(person);
      setReloadKey((k) => k + 1);
      setEmail("");
      setName("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveRename(person) {
    const newName = editName.trim();
    if (!newName) {
      setError("יש להזין שם");
      return;
    }
    if (newName === person.name) {
      setEditingId(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onRename(person, newName);
      setReloadKey((k) => k + 1);
      setEditingId(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!validEmail) {
      setError("יש להזין כתובת מייל תקינה");
      return;
    }
    if (alreadyIn(typed)) {
      setError("האדם כבר ברשימה");
      return;
    }
    let match = known;
    if (!match && !name.trim()) {
      // The address book may not have arrived yet (paste + immediate Enter): ask the server before calling it a new address
      try {
        const fresh = await api.listPeople();
        setPeople(fresh);
        match = fresh.find((p) => p.email === typed);
      } catch {
        // fall through to the "new address" message
      }
    }
    if (match) {
      add({ email: typed, name: match.name });
      return;
    }
    if (!name.trim()) {
      setError("מייל חדש בספר האנשים — יש להזין גם את השם המלא");
      return;
    }
    add({ email: typed, name: known ? known.name : name.trim() });
  }

  function handleKeyDown(e) {
    // Enter inside the source form must add the person, not submit the whole form
    if (e.key === "Enter") handleSubmit(e);
  }

  return (
    <div className="participants">
      <div className="tags-row">
        {participants.map((p) =>
          editingId === p.id ? (
            <span key={p.email} className="tag-chip participant-editing" title={p.email}>
              <input
                type="text"
                value={editName}
                autoFocus
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    e.stopPropagation();
                    saveRename(p);
                  } else if (e.key === "Escape") {
                    setEditingId(null);
                    setError("");
                  }
                }}
                disabled={busy}
              />
              <span className="muted"> {p.email}</span>
              <button type="button" className="tag-remove" title="שמור שם" onClick={() => saveRename(p)} disabled={busy}>
                ✓
              </button>
              <button type="button" className="tag-remove" title="ביטול" onClick={() => setEditingId(null)} disabled={busy}>
                ✕
              </button>
            </span>
          ) : (
            <span key={p.email} className="tag-chip" title={p.email}>
              {p.name}
              <span className="muted"> {p.email}</span>
              {!readOnly && onRename && p.id && (!p.registered || p.email === getStoredUser()?.email) && (
                <button
                  type="button"
                  className="tag-remove"
                  title="עריכת שם"
                  onClick={() => {
                    setEditingId(p.id);
                    setEditName(p.name);
                    setError("");
                  }}
                  disabled={disabled || busy}
                >
                  ✏️
                </button>
              )}
              {!readOnly && (
                <button type="button" className="tag-remove" onClick={() => onRemove(p)} disabled={disabled || busy}>
                  ×
                </button>
              )}
            </span>
          ),
        )}
        {participants.length === 0 && <span className="muted">אין משתתפים</span>}
      </div>

      {!readOnly && (
      <div className="participant-add">
        <input
          type="email"
          dir="ltr"
          placeholder="מייל"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setError("");
            setLoaded(true); // paste / autofill can change the value without a focus event
          }}
          onFocus={() => setLoaded(true)}
          onKeyDown={handleKeyDown}
          disabled={disabled || busy}
        />
        {validEmail && !known && (
          <input
            type="text"
            placeholder="שם מלא (מייל חדש)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled || busy}
          />
        )}
        {known && <span className="muted">{known.name}</span>}
        <button type="button" className="btn" onClick={handleSubmit} disabled={disabled || busy || !validEmail}>
          + הוסף
        </button>
      </div>
      )}

      {suggestions.length > 0 && (
        <div className="tag-suggest">
          <span className="muted">מהספר:</span>
          {suggestions.map((p) => (
            <button key={p.id} type="button" className="tag-chip tag-chip-suggest" onClick={() => add(p)}>
              {p.name}
              <span className="muted"> {p.email}</span>
            </button>
          ))}
        </div>
      )}
      {error && <div className="error-text">{error}</div>}
    </div>
  );
}
