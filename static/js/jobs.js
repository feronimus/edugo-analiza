// Analyses run in the program, not in the page: this module only watches them, so moving between screens never
// stops an analysis. Screens subscribe to changes; a finished analysis opens or shows a notice.
import { api, store } from "./api.js";
import { t } from "./i18n.js";
import { toast } from "./ui.js";

const listeners = new Set();
let list = [];
let timer = null;
let focused = null;          // the analysis the user just started from the form: opened automatically when done

export const jobs = {
  get list() { return list; },
  get active() { return list.filter(j => j.status === "queued" || j.status === "running"); },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },

  async start(fields, focus = true) {
    const job = await api.start({ mode: store.get("edugo_mode") || "balanced", ...fields });
    if (focus) focused = job.id;
    await refresh();
    return job;
  },
  async cancel(id) { await api.cancel(id).catch(() => {}); await refresh(); },
  refresh,
};

async function refresh() {
  clearTimeout(timer);
  let next = list;
  try { next = await api.jobs(); } catch (e) { /* the program restarts or is busy: keep the last state */ }
  for (const job of next) {
    const before = list.find(j => j.id === job.id);
    if (before && before.status !== "done" && job.status === "done") finished(job);
  }
  list = next;
  listeners.forEach(fn => fn(list));
  timer = setTimeout(refresh, jobs.active.length ? 1500 : 10000);
}

function finished(job) {
  const open = store.get("edugo_autoopen") !== "0";
  const onAnalysis = location.hash === "" || location.hash === "#/" || location.hash === "#";
  if (open && job.id === focused && onAnalysis) {
    location.hash = `#/wynik/${job.id}`;
  } else {
    toast(t("Analiza gotowa: ", "Analysis ready: ") + (job.label || ""), { href: `#/wynik/${job.id}`, label: t("Zobacz wynik", "See the result") });
  }
  if (job.id === focused) focused = null;
}

/** Overall progress 0..1 across the stages of one analysis. */
export function stageProgress(job) {
  const order = ["download", "decode", "models", "asr", "done"];
  const i = order.indexOf(job.stage);
  return i < 0 ? 0 : Math.min(1, (i + (job.progress || 0)) / order.length);
}
