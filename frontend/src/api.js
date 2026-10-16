const BASE_URL = "http://localhost:8000";

// The login lives in sessionStorage: every browser tab is its own session, so two different users can be tried side
// by side in two tabs. Closing the tab logs out.
const TOKEN_KEY = "om_token";
const USER_KEY = "om_user";

function readStore(key) {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStore(key, value) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch {
    // storage blocked: the login just won't survive a reload
  }
}

export function getToken() {
  return readStore(TOKEN_KEY);
}

export function getStoredUser() {
  try {
    return JSON.parse(readStore(USER_KEY) || "null");
  } catch {
    return null;
  }
}

export function saveLogin({ token, user }) {
  writeStore(TOKEN_KEY, token);
  writeStore(USER_KEY, JSON.stringify(user));
}

export function clearLogin() {
  writeStore(TOKEN_KEY, null);
  writeStore(USER_KEY, null);
}

function apiFetch(url, options = {}) {
  const token = getToken();
  const headers = token ? { ...(options.headers || {}), Authorization: `Bearer ${token}` } : options.headers;
  return fetch(url, { ...options, headers });
}

async function handle(res) {
  if (res.status === 401 && getToken()) {
    clearLogin();
    window.dispatchEvent(new Event("auth-expired"));
  }
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

export const ROLE_LABELS = { owner: "בעלים", editor: "עורך", viewer: "צופה" };

export const api = {
  // auth
  register: (email, name, password) =>
    apiFetch(`${BASE_URL}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, name, password }),
    }).then(handle),
  login: (email, password) =>
    apiFetch(`${BASE_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }).then(handle),
  logout: () => apiFetch(`${BASE_URL}/api/auth/logout`, { method: "POST" }).then(handle),
  me: () => apiFetch(`${BASE_URL}/api/auth/me`).then(handle),

  // topics
  listTopics: (q) => apiFetch(`${BASE_URL}/api/topics${q ? `?q=${encodeURIComponent(q)}` : ""}`).then(handle),
  getTopic: (id) => apiFetch(`${BASE_URL}/api/topics/${id}`).then(handle),
  createTopic: (data) =>
    apiFetch(`${BASE_URL}/api/topics`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handle),
  updateTopic: (id, data) =>
    apiFetch(`${BASE_URL}/api/topics/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handle),
  deleteTopic: (id) => apiFetch(`${BASE_URL}/api/topics/${id}`, { method: "DELETE" }).then(handle),
  askAi: (id, question, chatId = null, file = null, tag = null) => {
    const fd = new FormData();
    fd.append("question", question);
    if (chatId) fd.append("chat_id", chatId);
    if (file) fd.append("file", file);
    if (tag) fd.append("tag", tag);
    return apiFetch(`${BASE_URL}/api/topics/${id}/ask`, { method: "POST", body: fd }).then(handle);
  },

  // chats
  listChats: (topicId) => apiFetch(`${BASE_URL}/api/topics/${topicId}/chats`).then(handle),
  getChat: (chatId) => apiFetch(`${BASE_URL}/api/chats/${chatId}`).then(handle),
  renameChat: (chatId, title) =>
    apiFetch(`${BASE_URL}/api/chats/${chatId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }).then(handle),
  deleteChat: (chatId) => apiFetch(`${BASE_URL}/api/chats/${chatId}`, { method: "DELETE" }).then(handle),

  // sources
  listSources: (topicId) => apiFetch(`${BASE_URL}/api/topics/${topicId}/sources`).then(handle),
  createSource: (topicId, formData) =>
    apiFetch(`${BASE_URL}/api/topics/${topicId}/sources`, {
      method: "POST",
      body: formData,
    }).then(handle),
  getSource: (id) => apiFetch(`${BASE_URL}/api/sources/${id}`).then(handle),
  updateSource: (id, data) =>
    apiFetch(`${BASE_URL}/api/sources/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then(handle),
  deleteSource: (id) => apiFetch(`${BASE_URL}/api/sources/${id}`, { method: "DELETE" }).then(handle),
  analyzeSource: (id) => apiFetch(`${BASE_URL}/api/sources/${id}/analyze`, { method: "POST" }).then(handle),
  addTag: (sourceId, name) =>
    apiFetch(`${BASE_URL}/api/sources/${sourceId}/tags`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then(handle),
  removeTag: (sourceId, tagId) =>
    apiFetch(`${BASE_URL}/api/sources/${sourceId}/tags/${tagId}`, { method: "DELETE" }).then(handle),

  // topic sharing
  listMembers: (topicId) => apiFetch(`${BASE_URL}/api/topics/${topicId}/members`).then(handle),
  addMember: (topicId, member) =>
    apiFetch(`${BASE_URL}/api/topics/${topicId}/members`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(member),
    }).then(handle),
  updateMember: (topicId, personId, role) =>
    apiFetch(`${BASE_URL}/api/topics/${topicId}/members/${personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }).then(handle),
  removeMember: (topicId, personId) =>
    apiFetch(`${BASE_URL}/api/topics/${topicId}/members/${personId}`, { method: "DELETE" }).then(handle),

  // people / participants
  listPeople: () => apiFetch(`${BASE_URL}/api/people`).then(handle),
  renamePerson: (personId, name) =>
    apiFetch(`${BASE_URL}/api/people/${personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then(handle),
  addParticipant: (sourceId, person) =>
    apiFetch(`${BASE_URL}/api/sources/${sourceId}/participants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(person),
    }).then(handle),
  removeParticipant: (sourceId, personId) =>
    apiFetch(`${BASE_URL}/api/sources/${sourceId}/participants/${personId}`, { method: "DELETE" }).then(handle),

  // tags
  listTags: () => apiFetch(`${BASE_URL}/api/tags`).then(handle),
  similarTags: (name) => apiFetch(`${BASE_URL}/api/tags/similar?name=${encodeURIComponent(name)}`).then(handle),
  tagCleanup: () => apiFetch(`${BASE_URL}/api/tags/cleanup`).then(handle),
  mergeTag: (tagId, intoId) =>
    apiFetch(`${BASE_URL}/api/tags/${tagId}/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ into_id: intoId }),
    }).then(handle),
  suggestTagSynonyms: () => apiFetch(`${BASE_URL}/api/tags/synonyms`, { method: "POST" }).then(handle),
  mergeTagGroup: (keepId, mergeIds) =>
    apiFetch(`${BASE_URL}/api/tags/merge-group`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keep_id: keepId, merge_ids: mergeIds }),
    }).then(handle),
  deleteUnusedTags: (tagIds) =>
    apiFetch(`${BASE_URL}/api/tags/delete-unused`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag_ids: tagIds }),
    }).then(handle),
  splitTag: (tagId) => apiFetch(`${BASE_URL}/api/tags/${tagId}/split`, { method: "POST" }).then(handle),
  sourcesByTag: (name) => apiFetch(`${BASE_URL}/api/tags/${encodeURIComponent(name)}/sources`).then(handle),
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
