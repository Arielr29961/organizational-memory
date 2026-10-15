import { useState } from "react";
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

export default function AskAI({ topicId, onOpenSource }) {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState([]);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");

  async function handleAsk(q) {
    const finalQuestion = (q ?? question).trim();
    if (!finalQuestion) return;
    setAsking(true);
    setError("");
    setQuestion("");
    try {
      const res = await api.askAi(topicId, finalQuestion);
      setHistory((h) => [...h, { question: finalQuestion, answer: res.answer, usedSources: res.used_sources }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="ask-ai">
      <div className="example-questions">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button key={q} className="chip-btn" onClick={() => handleAsk(q)} disabled={asking}>
            {q}
          </button>
        ))}
      </div>

      <div className="chat-history">
        {history.map((turn, idx) => (
          <div key={idx} className="chat-turn">
            <div className="chat-question">{turn.question}</div>
            <div className="chat-answer">
              <AnswerText
                text={turn.answer}
                sourcesById={Object.fromEntries(turn.usedSources.map((s) => [s.id, s]))}
                onOpenSource={onOpenSource}
              />
            </div>
            {turn.usedSources.length > 0 && (
              <div className="chat-sources">
                מקורות שצוטטו:{" "}
                {turn.usedSources.map((s) => (
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
        ))}
        {asking && <div className="muted">חושב...</div>}
        {error && <div className="error-text">{error}</div>}
      </div>

      <form
        className="ask-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          handleAsk();
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="שאלו כל שאלה על הנושא הזה..."
          disabled={asking}
        />
        <button type="submit" className="btn btn-primary" disabled={asking}>
          שלח
        </button>
      </form>
    </div>
  );
}
