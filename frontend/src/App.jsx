import { useEffect, useState } from "react";
import { api } from "./api";
import Sidebar from "./components/Sidebar";
import TopicView from "./components/TopicView";
import AddTopicModal from "./components/AddTopicModal";

export default function App() {
  const [topics, setTopics] = useState([]);
  const [selectedTopicId, setSelectedTopicId] = useState(null);
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
        onSelect={setSelectedTopicId}
        search={search}
        onSearchChange={setSearch}
        onAddTopic={() => setShowAddTopic(true)}
        loading={loading}
        error={error}
      />
      <main className="main-area">
        {selectedTopicId ? (
          <TopicView
            topicId={selectedTopicId}
            onTopicChanged={refreshTopics}
            onTopicDeleted={handleTopicDeleted}
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
