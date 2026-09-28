const BASE_URL = "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    let message = `שגיאה בבקשה (${res.status})`;
    try {
      const data = await res.json();
      if (data.detail) message = data.detail;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // topics
  listTopics: (q) => fetch(`${BASE_URL}/api/topics${q ? `?q=${encodeURIComponent(q)}` : ""}`).then(handle),
  getTopic: (id) => fetch(`${BASE_URL}/api/topics/${id}`).then(handle),
  createTopic: (data) =>
    fetch(`${BASE_URL}/api/topics`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handle),
  updateTopic: (id, data) =>
    fetch(`${BASE_URL}/api/topics/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handle),
  deleteTopic: (id) => fetch(`${BASE_URL}/api/topics/${id}`, { method: "DELETE" }).then(handle),
  topicInsights: (id) => fetch(`${BASE_URL}/api/topics/${id}/insights`).then(handle),
  topicConnections: (id) => fetch(`${BASE_URL}/api/topics/${id}/connections`).then(handle),
  askAi: (id, question) =>
    fetch(`${BASE_URL}/api/topics/${id}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then(handle),

  // sources
  listSources: (topicId) => fetch(`${BASE_URL}/api/topics/${topicId}/sources`).then(handle),
  createSource: (topicId, formData) =>
    fetch(`${BASE_URL}/api/topics/${topicId}/sources`, {
      method: "POST",
      body: formData,
    }).then(handle),
  getSource: (id) => fetch(`${BASE_URL}/api/sources/${id}`).then(handle),
  updateSource: (id, data) =>
    fetch(`${BASE_URL}/api/sources/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handle),
  deleteSource: (id) => fetch(`${BASE_URL}/api/sources/${id}`, { method: "DELETE" }).then(handle),
  analyzeSource: (id) => fetch(`${BASE_URL}/api/sources/${id}/analyze`, { method: "POST" }).then(handle),
  addTag: (sourceId, name) =>
    fetch(`${BASE_URL}/api/sources/${sourceId}/tags`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then(handle),
  removeTag: (sourceId, tagId) =>
    fetch(`${BASE_URL}/api/sources/${sourceId}/tags/${tagId}`, { method: "DELETE" }).then(handle),

  // tags
  listTags: () => fetch(`${BASE_URL}/api/tags`).then(handle),
  sourcesByTag: (name) => fetch(`${BASE_URL}/api/tags/${encodeURIComponent(name)}/sources`).then(handle),
};

export const SOURCE_TYPES = [
  { value: "meeting_transcript", label: "תמלול פגישה" },
  { value: "meeting_summary", label: "סיכום פגישה" },
  { value: "email", label: "מייל" },
  { value: "presentation", label: "מצגת" },
  { value: "spreadsheet", label: "קובץ אקסל / CSV" },
  { value: "document", label: "מסמך" },
  { value: "other", label: "אחר" },
];

export const SOURCE_TYPE_LABELS = Object.fromEntries(SOURCE_TYPES.map((t) => [t.value, t.label]));

export const INSIGHT_TYPE_LABELS = {
  fact: "עובדה",
  decision: "החלטה",
  hypothesis: "השערה",
  open_question: "שאלה פתוחה",
  action_item: "משימה נדרשת",
};
