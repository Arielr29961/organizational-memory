import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import AnswerText from "./AnswerText";

const EXAMPLE_QUESTIONS = [
  "מה קרה בנושא הזה לאורך זמן?",
  "מהן השאלות הפתוחות החשובות ביותר?",
  "אילו החלטות התקבלו?",
  "מה השתנה מאז הפגישה הקודמת?",
  "אילו משימות פתוחות עדיין נותרו?",
  "האם יש סתירות בין המקורות השונים?",
  "אילו מקורות מנושאים אחרים עשויים להיות רלוונטיים?",
  "תכין אותי לפגישה הבאה בנושא הזה",
  "מה אנחנו יודעים, מה אנחנו חושבים שאנחנו יודעים, ומה עדיין לא ידוע?",
];

// activeChatId: undefined = not chosen yet (open the latest chat), null = a new empty chat, string = that chat.
export default function AskAI({ topicId, onOpenSource, activeChatId, onActiveChatChange }) {
  const [chats, setChats] = useState([]);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [attachment, setAttachment] = useState(null);
  const [asking, setAsking] = useState(false);
  const [loadingChat, setLoadingChat] = useState(false);
  const [error, setError] = useState("");
  // The chat whose messages are currently in `messages`, so we don't re-fetch a chat we just built locally.
  const loadedChatId = useRef(null);

  async function refreshChats() {
    const list = await api.listChats(topicId);
    setChats(list);
    return list;
  }

  useEffect(() => {
    let cancelled = false;
    refreshChats()
      .then((list) => {
        if (!cancelled && activeChatId === undefined) onActiveChatChange(list[0]?.id ?? null);
      })
      .catch((err) => setError(err.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicId]);

  useEffect(() => {
    if (activeChatId === undefined) return;
    if (activeChatId === null) {
      loadedChatId.current = null;
      setMessages([]);
      return;
    }
    if (loadedChatId.current === activeChatId) return;
    let cancelled = false;
    setLoadingChat(true);
    api
      .getChat(activeChatId)
      .then((chat) => {
        if (cancelled) return;
        loadedChatId.current = chat.id;
        setMessages(chat.messages);
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoadingChat(false));
    return () => {
      cancelled = true;
    };
  }, [activeChatId]);

  async function handleAsk(q) {
    const finalQuestion = (q ?? question).trim();
    if (!finalQuestion || asking) return;
    setAsking(true);
    setError("");
    const file = attachment;
    setQuestion("");
    setAttachment(null);
    setMessages((m) => [
      ...m,
      { id: `pending-${Date.now()}`, role: "user", content: finalQuestion, attachment_name: file?.name, used_sources: [] },
    ]);
    try {
      const res = await api.askAi(topicId, finalQuestion, activeChatId ?? null, file);
      setMessages((m) => [
        ...m,
        { id: `answer-${Date.now()}`, role: "assistant", content: res.answer, used_sources: res.used_sources },
      ]);
      loadedChatId.current = res.chat_id;
      if (res.chat_id !== activeChatId) onActiveChatChange(res.chat_id);
      await refreshChats();
    } catch (err) {
      setError(err.message);
      setMessages((m) => m.slice(0, -1));
      setQuestion(finalQuestion);
      setAttachment(file);
    } finally {
      setAsking(false);
    }
  }

  async function handleRename(chat) {
    const title = prompt("שם חדש לשיחה:", chat.title)?.trim();
    if (!title || title === chat.title) return;
    try {
      await api.renameChat(chat.id, title);
      await refreshChats();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(chat) {
    if (!confirm(`למחוק את השיחה "${chat.title}"? פעולה זו אינה הפיכה.`)) return;
    try {
      await api.deleteChat(chat.id);
      if (chat.id === activeChatId) onActiveChatChange(null);
      await refreshChats();
    } catch (err) {
      setError(err.message);
    }
  }

  function renderTurn(message, index) {
    if (message.role === "user") {
      return (
        <div key={message.id} className="chat-turn chat-turn-user">
          {message.attachment_name && <div className="file-chip">📎 {message.attachment_name}</div>}
          <div className="chat-question">{message.content}</div>
        </div>
      );
    }
    const sources = message.used_sources || [];
    return (
      <div key={message.id || index} className="chat-turn">
        <div className="chat-answer">
          <AnswerText
            text={message.content}
            sourcesById={Object.fromEntries(sources.map((s) => [s.id, s]))}
            onOpenSource={onOpenSource}
          />
        </div>
        {sources.length > 0 && (
          <div className="chat-sources">
            מקורות שצוטטו:{" "}
            {sources.map((s) => (
              <button
                key={s.id}
                type="button"
                className="source-link"
                title={s.topic_name}
                onClick={() => onOpenSource(s.topic_id, s.id)}
              >
                {s.title}, {s.date}
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="ask-layout">
      <aside className="chat-list">
        <button className="btn btn-primary" onClick={() => onActiveChatChange(null)} disabled={asking}>
          + שיחה חדשה
        </button>
        {chats.length === 0 && <div className="muted">עדיין אין שיחות שמורות</div>}
        {chats.map((chat) => (
          <div key={chat.id} className={`chat-list-item ${chat.id === activeChatId ? "active" : ""}`}>
            <button
              className="chat-list-title"
              onClick={() => onActiveChatChange(chat.id)}
              disabled={asking}
              title={chat.title}
            >
              {chat.title}
            </button>
            <button className="btn-icon" onClick={() => handleRename(chat)} title="שינוי שם">
              ✎
            </button>
            <button className="btn-icon" onClick={() => handleDelete(chat)} title="מחיקת שיחה">
              🗑
            </button>
          </div>
        ))}
      </aside>

      <div className="ask-ai">
        {messages.length === 0 && !loadingChat && (
          <div className="example-questions">
            {EXAMPLE_QUESTIONS.map((q) => (
              <button key={q} className="chip-btn" onClick={() => handleAsk(q)} disabled={asking}>
                {q}
              </button>
            ))}
          </div>
        )}

        <div className="chat-history">
          {loadingChat && <div className="muted">טוען שיחה...</div>}
          {messages.map(renderTurn)}
          {asking && <div className="muted">חושב...</div>}
          {error && <div className="error-text">{error}</div>}
        </div>

        {attachment && (
          <div className="attachment-bar">
            <span className="file-chip">📎 {attachment.name}</span>
            <button type="button" className="btn-icon" onClick={() => setAttachment(null)} title="הסרת הקובץ">
              ×
            </button>
          </div>
        )}

        <form
          className="ask-input-row"
          onSubmit={(e) => {
            e.preventDefault();
            handleAsk();
          }}
        >
          <label className="btn attach-btn" title="צירוף קובץ (PDF, Word, Excel, CSV, טקסט)">
            📎
            <input
              type="file"
              accept=".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md"
              disabled={asking}
              onChange={(e) => {
                setAttachment(e.target.files[0] || null);
                e.target.value = "";
              }}
            />
          </label>
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder={messages.length ? "המשיכו את השיחה..." : "שאלו כל שאלה על הנושא הזה..."}
            disabled={asking}
          />
          <button type="submit" className="btn btn-primary" disabled={asking}>
            שלח
          </button>
        </form>
      </div>
    </div>
  );
}
