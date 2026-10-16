import { useEffect, useState } from "react";
import { api, clearLogin, getStoredUser, getToken, saveLogin } from "./api";
import Login from "./components/Login";
import Sidebar from "./components/Sidebar";
import TopicView from "./components/TopicView";
import AddTopicModal from "./components/AddTopicModal";
import IntakeInbox from "./components/IntakeInbox";

function Workspace({ user, onLogout }) {
  const [topics, setTopics] = useState([]);
  const [selectedTopicId, setSelectedTopicId] = useState(null);
  const [view, setView] = useState("topics"); // "topics" | "intake"
  const [intakeCount, setIntakeCount] = useState(0);
  const [focusSource, setFocusSource] = useState(null);
  const [search, setSearch] = useState("");
  const [showAddTopic, setShowAddTopic] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function refreshTopics() {
    try {
      const data = await api.listTopics(search);
      setTopics(data);
      return data;
    } catch (e) {
      setError(e.message);
      return [];
    }
  }

  // The badge on the inbox button: proposals still open
  useEffect(() => {
    api.listIntake().then((l) => setIntakeCount(l.length)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    refreshTopics().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  async function handleCreateTopic(payload) {
    const topic = await api.createTopic(payload);
    setShowAddTopic(false);
    await refreshTopics();
    setSelectedTopicId(topic.id);
    setView("topics");
  }

  // Jump to a source's card in its topic's timeline (a new object each time so repeated clicks re-trigger).
  function handleOpenSource(topicId, sourceId) {
    setSelectedTopicId(topicId);
    setView("topics");
    setFocusSource({ topicId, sourceId });
  }

  async function handleTopicDeleted(topicId) {
    if (selectedTopicId === topicId) setSelectedTopicId(null);
    await refreshTopics();
  }

  return (
    <div className="app-shell">
      <Sidebar
        topics={topics}
        selectedTopicId={selectedTopicId}
        onSelect={(id) => {
          setSelectedTopicId(id);
          setView("topics");
        }}
        intakeCount={intakeCount}
        intakeActive={view === "intake"}
        onOpenIntake={() => setView("intake")}
        search={search}
        onSearchChange={setSearch}
        onAddTopic={() => setShowAddTopic(true)}
        loading={loading}
        error={error}
        user={user}
        onLogout={onLogout}
      />
      <main className="main-area">
        {view === "intake" ? (
          <IntakeInbox onCountChange={setIntakeCount} onSourcesAdded={refreshTopics} />
        ) : selectedTopicId ? (
          <TopicView
            topicId={selectedTopicId}
            onTopicChanged={refreshTopics}
            onTopicDeleted={handleTopicDeleted}
            focusSource={focusSource}
            onOpenSource={handleOpenSource}
          />
        ) : (
          <div className="empty-state">
            <h2>ברוכים הבאים לזיכרון הארגוני</h2>
            <p>בחרו נושא קיים מהתפריט מימין, או צרו נושא חדש כדי להתחיל לצבור ידע.</p>
            <button className="btn btn-primary" onClick={() => setShowAddTopic(true)}>
              + נושא חדש
            </button>
          </div>
        )}
      </main>

      {showAddTopic && (
        <AddTopicModal onClose={() => setShowAddTopic(false)} onCreate={handleCreateTopic} />
      )}
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(() => (getToken() ? getStoredUser() : null));
  const [checking, setChecking] = useState(() => Boolean(getToken()));

  // Validate a stored login once on load; an expired one falls back to the login screen
  useEffect(() => {
    if (!getToken()) return;
    api
      .me()
      .then((u) => setUser(u))
      .catch(() => {
        clearLogin();
        setUser(null);
      })
      .finally(() => setChecking(false));
  }, []);

  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener("auth-expired", onExpired);
    return () => window.removeEventListener("auth-expired", onExpired);
  }, []);

  function handleLogin(result) {
    saveLogin(result);
    setUser(result.user);
  }

  async function handleLogout() {
    try {
      await api.logout();
    } catch {
      // the token is dropped locally either way
    }
    clearLogin();
    setUser(null);
  }

  if (checking) return <div className="muted" style={{ padding: 24 }}>טוען...</div>;
  if (!user) return <Login onLogin={handleLogin} />;
  // key: a different user gets a fresh workspace, never the previous user's state
  return <Workspace key={user.id} user={user} onLogout={handleLogout} />;
}
