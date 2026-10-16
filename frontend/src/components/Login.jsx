import { useState } from "react";
import { api } from "../api";

// Sign in / create account. A person who is already in the address book (e.g. added as a participant) claims
// that address by registering with it.
export default function Login({ onLogin }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result =
        mode === "login" ? await api.login(email, password) : await api.register(email, name, password);
      onLogin(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const isLogin = mode === "login";

  return (
    <div className="auth-page">
      <form className="auth-card form" onSubmit={handleSubmit}>
        <h1>זיכרון ארגוני</h1>
        <p className="sidebar-subtitle">{isLogin ? "כניסה לחשבון" : "יצירת חשבון חדש"}</p>

        <label>
          מייל
          <input type="email" dir="ltr" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </label>
        {!isLogin && (
          <label>
            שם מלא
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        <label>
          סיסמה {!isLogin && <span className="muted">(לפחות 8 תווים)</span>}
          <input
            type="password"
            dir="ltr"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={isLogin ? undefined : 8}
          />
        </label>

        {error && <div className="error-text">{error}</div>}

        <button type="submit" className="btn btn-primary btn-block" disabled={busy}>
          {busy ? "..." : isLogin ? "כניסה" : "יצירת חשבון"}
        </button>
        <button
          type="button"
          className="link-btn"
          onClick={() => {
            setMode(isLogin ? "register" : "login");
            setError("");
          }}
        >
          {isLogin ? "אין חשבון? יצירת חשבון" : "כבר יש חשבון? כניסה"}
        </button>
      </form>
    </div>
  );
}
