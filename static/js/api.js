// Talking to the local program, and the browser's own small storage for settings.

export const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private window: settings are not kept */ } },
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function call(method, url, form) {
  let response;
  try {
    response = await fetch(url, { method, body: form });
  } catch (e) {
    throw new ApiError("Program nie odpowiada. Uruchom „eduGO Analiza” ponownie z pulpitu.", 0);
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(body.detail || "Błąd programu", response.status);
  return body;
}

const form = fields => {
  const f = new FormData();
  for (const [k, v] of Object.entries(fields)) f.append(k, v);
  return f;
};

export const api = {
  health: () => call("GET", "/api/health"),
  jobs: () => call("GET", "/api/jobs"),
  job: id => call("GET", `/api/jobs/${id}`),
  start: fields => call("POST", "/api/jobs", form(fields)),
  cancel: id => call("POST", `/api/jobs/${id}/cancel`),
  history: () => call("GET", "/api/history"),
  historyItem: id => call("GET", `/api/history/${id}`),
  setTeacher: (id, teacher) => call("POST", `/api/history/${id}/teacher`, form({ teacher })),
  deleteItem: id => call("DELETE", `/api/history/${id}`),
  update: (force = false) => call("GET", `/api/update${force ? "?force=true" : ""}`),
  installUpdate: () => call("POST", "/api/update"),
  feedbackEnabled: () => call("GET", "/api/feedback"),
  sendFeedback: text => call("POST", "/api/feedback", form({ text })),
  openData: () => call("POST", "/api/open-data"),
  csvUrl: id => `/api/jobs/${id}/wyniki.csv`,
};
