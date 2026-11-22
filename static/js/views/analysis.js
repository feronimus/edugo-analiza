// "Analiza": start an analysis (one link, a file, or several links) and follow the running ones.
import { jobs, stageProgress } from "../jobs.js";
import { t, tr } from "../i18n.js";
import { icon, title } from "../icons.js";
import { $, clock, esc } from "../ui.js";

const STAGES = [["download", "Pobieranie", "Download"], ["decode", "Odczyt dźwięku", "Reading audio"],
  ["models", "Przygotowanie", "Preparing"], ["asr", "Rozpoznawanie mowy", "Speech recognition"], ["done", "Wyniki", "Results"]];
let unsubscribe = null;
let shape = "";             // ids and states of the cards on screen

export function render(root) {
  root.innerHTML = `
    <section class="card">
      <h1>${t("Nowa analiza", "New analysis")}</h1>
      <p class="muted">${t("Program słucha nagrania na tym komputerze i liczy, ile nauczyciel i uczniowie mówią po angielsku.", "The program listens to the recording on this computer and measures how much English the teacher and the students speak.")}</p>
      <label class="lbl" for="url">${t("Link do nagrania z Dropboxa", "Dropbox link to the recording")}</label>
      <div class="row">
        <div class="input-ic">${icon("link")}<input type="text" id="url" placeholder="https://www.dropbox.com/scl/fi/…" autocomplete="off"></div>
        <button class="btn" id="startBtn" type="button">${icon("play", 16)}${t("Rozpocznij analizę", "Start analysis")}</button>
      </div>
      <p class="hint">${t("Nagranie nie jest nigdzie przechowywane – po analizie program je usuwa.", "The recording is not stored anywhere – it is deleted after the analysis.")}
        <button class="link" id="fileBtn" type="button">${icon("file", 14)}${t("…albo wybierz plik z komputera", "…or choose a file from your computer")}</button>
        <input type="file" id="file" accept="video/*,audio/*" hidden></p>
      <details class="more">
        <summary>${icon("queue", 16)}${t("Kilka nagrań naraz", "Several recordings at once")}</summary>
        <label class="lbl" for="batch">${t("Jeden link w wierszu – program przeanalizuje je po kolei", "One link per line – they are analysed one after another")}</label>
        <textarea id="batch" rows="3" placeholder="https://www.dropbox.com/scl/fi/…"></textarea>
        <button class="btn2" id="batchBtn" type="button">${icon("queue", 16)}${t("Dodaj do kolejki", "Add to queue")}</button>
      </details>
      <p class="err" id="formErr" hidden></p>
    </section>
    <section id="queue"></section>`;

  $("startBtn").onclick = () => startOne();
  $("url").addEventListener("keydown", e => { if (e.key === "Enter") startOne(); });
  $("fileBtn").onclick = () => $("file").click();
  $("file").onchange = () => { if ($("file").files[0]) startOne($("file").files[0]); };
  $("batchBtn").onclick = startBatch;
  unsubscribe = jobs.subscribe(paintQueue);
  paintQueue(jobs.list);
  $("url").focus();
}

export function leave() {
  shape = "";
  if (unsubscribe) unsubscribe();
}

function showError(message) {
  $("formErr").textContent = tr(message);
  $("formErr").hidden = !message;
}

async function startOne(file) {
  showError("");
  const url = $("url").value.trim();
  if (!file && !url) { showError("Wklej link do nagrania."); return; }
  $("startBtn").disabled = true;
  try {
    await jobs.start(file ? { file } : { url });
    $("url").value = "";
  } catch (e) { showError(e.message); }
  $("startBtn").disabled = false;
  $("file").value = "";
}

async function startBatch() {
  showError("");
  const links = $("batch").value.split(/\s+/).filter(l => /^https?:\/\//.test(l));
  if (!links.length) { showError("Wklej link do nagrania."); return; }
  for (const url of links) {
    try { await jobs.start({ url }, false); } catch (e) { showError(e.message); }
  }
  $("batch").value = "";
}

function paintQueue(list) {
  const box = $("queue");
  if (!box) return;
  const now = list.map(j => `${j.id}:${j.status}`).join(",");
  if (now === shape && list.length) { list.forEach(updateCard); return; }
  shape = now;
  if (!list.length) { box.innerHTML = howItWorks(); return; }
  box.innerHTML = title("queue", t("Analizy w tej sesji", "Analyses in this session")) +
    list.map(jobCard).join("");
  box.querySelectorAll("[data-cancel]").forEach(b => { b.onclick = () => jobs.cancel(b.dataset.cancel); });
}

function jobCard(job) {
  const state = { queued: ["w kolejce", "queued"], running: ["trwa", "running"], done: ["gotowa", "done"],
    error: ["błąd", "error"], cancelled: ["przerwana", "cancelled"] }[job.status] || [job.status, job.status];
  const stageIndex = STAGES.findIndex(s => s[0] === job.stage);
  const busy = job.status === "queued" || job.status === "running";
  return `<article class="card job ${job.status}" data-job="${esc(job.id)}">
    <div class="job-head">
      <div class="job-name">${esc(job.label || t("nagranie", "recording"))}</div>
      <span class="chip ${job.status}">${t(...state)}</span>
    </div>
    ${busy ? `<div class="bar"><div style="width:${Math.max(2, 100 * stageProgress(job))}%"></div></div>
      <div class="steps">${STAGES.map((s, i) => `<span class="${i < stageIndex ? "ok" : i === stageIndex ? "on" : ""}">${t(s[1], s[2])}</span>`).join("")}</div>
      <div class="job-foot"><span class="muted msg-line">${job.status === "running" ? '<span class="spinner" aria-hidden="true"></span>' : ""}<span class="msg">${statusLine(job)}</span></span>
        <button class="btn2 small" type="button" data-cancel="${esc(job.id)}">${icon("close", 15)}${t("Przerwij", "Cancel")}</button></div>` : ""}
    ${job.status === "done" ? `<div class="job-foot"><span class="muted">${job.elapsed_s ? t("czas analizy ", "analysis time ") + clock(job.elapsed_s) : ""}</span>
      <a class="btn small" href="#/wynik/${esc(job.id)}">${icon("chart", 15)}${t("Zobacz wynik", "See the result")}</a></div>` : ""}
    ${job.status === "error" || job.status === "cancelled" ? `<p class="err">${esc(tr(job.error) || "")}</p>` : ""}
  </article>`;
}

function statusLine(job) {
  return (job.status === "queued" && job.queue_position ? t(`W kolejce przed tą analizą: ${job.queue_position}`, `Ahead of this one: ${job.queue_position}`)
    : esc(tr(job.message) || "")) + (job.elapsed_s ? ` · ${clock(job.elapsed_s)}` : "");
}

/** Move the bar, the stage and the message of a card that is already on screen. */
function updateCard(job) {
  const card = document.querySelector(`[data-job="${CSS.escape(job.id)}"]`);
  if (!card || (job.status !== "running" && job.status !== "queued")) return;
  const bar = card.querySelector(".bar > div");
  if (bar) bar.style.width = `${Math.max(2, 100 * stageProgress(job))}%`;
  const msg = card.querySelector(".msg");
  if (msg) msg.innerHTML = statusLine(job);
  const stageIndex = STAGES.findIndex(s => s[0] === job.stage);
  card.querySelectorAll(".steps span").forEach((el, i) => { el.className = i < stageIndex ? "ok" : i === stageIndex ? "on" : ""; });
}

function howItWorks() {
  const step = (n, pl, en) => `<li><span class="n">${n}</span><span>${t(pl, en)}</span></li>`;
  return `<section class="card soft">${title("info", t("Jak to działa", "How it works"))}<ol class="how">
    ${step(1, "Wklej link do nagrania z arkusza i kliknij <b>Rozpocznij analizę</b>.", "Paste the recording link from the spreadsheet and click <b>Start analysis</b>.")}
    ${step(2, "Program pobiera nagranie i analizuje je na tym komputerze – trwa to zwykle 2–4 minuty. W tym czasie możesz przejść do innych zakładek.", "The program downloads the recording and listens to it on this computer – usually 2–4 minutes. You can use other tabs meanwhile.")}
    ${step(3, "Wynik otworzy się sam i trafi do <b>Historii</b>.", "The result opens by itself and is saved in <b>History</b>.")}
  </ol></section>`;
}
