import { useState } from "react";
import Modal from "./Modal";

export default function AddTopicModal({ onClose, onCreate }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      await onCreate({ name: name.trim(), description: description.trim() });
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal title="נושא חדש" onClose={onClose}>
      <form onSubmit={handleSubmit} className="form">
        <label>
          שם הנושא
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="לדוגמה: Recovery, תמחור, מדיניות אשראי"
            autoFocus
            required
          />
        </label>
        <label>
          תיאור (אופציונלי)
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="כמה מילים על הנושא..."
          />
        </label>
        {error && <div className="error-text">{error}</div>}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>
            ביטול
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "שומר..." : "צור נושא"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
