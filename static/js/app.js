// The app shell: menu, screens (one page, browser Back works), progress badge and the update banner.
import { api } from "./api.js";
import { LANG, setLang, t, tr } from "./i18n.js";
import { jobs, stageProgress } from "./jobs.js";
import { icon } from "./icons.js";
import { $, esc, pct } from "./ui.js";
import * as analysis from "./views/analysis.js";
import * as help from "./views/help.js";
import * as history from "./views/history.js";
import * as report from "./views/report.js";
import * as result from "./views/result.js";
import * as settings from "./views/settings.js";

const ROUTES = { "": analysis, historia: history, wynik: result, pomoc: help, ustawienia: settings, zglos: report };
const MENU = [["", "analysis", "Analiza", "Analysis"], ["historia", "history", "Historia", "History"],
  ["pomoc", "help", "Instrukcja", "Instructions"], ["ustawienia", "settings", "Ustawienia", "Settings"]];
let current = null;

function parseHash() {
  const [name = "", ...rest] = location.hash.replace(/^#\/?/, "").split("/");
  return { name: ROUTES[name] ? name : "", param: decodeURIComponent(rest.join("/")) };
}

function show() {
  const { name, param } = parseHash();
  if (current && current.leave) current.leave();
  current = ROUTES[name];
  $("view").dataset.ticket = String(Number($("view").dataset.ticket || 0) + 1);
  paintHeader();
  current.render($("view"), param);
  window.scrollTo(0, 0);
}

function paintHeader() {
  const { name } = parseHash();
  const active = name === "wynik" ? "historia" : name;
  $("brandName").textContent = t("Analiza lekcji", "Lesson analysis");
  $("menu").innerHTML = MENU.map(([route, ic, pl, en]) =>
    `<a href="#/${route}" class="${route === active ? "on" : ""}" ${route === active ? 'aria-current="page"' : ""}>${icon(ic, 17)}<span>${t(pl, en)}</span></a>`).join("");
  $("langSw").innerHTML = ["pl", "en"].map(l => `<button type="button" data-lang="${l}" aria-pressed="${l === LANG}">${l.toUpperCase()}</button>`).join("");
  $("footer").innerHTML = `<a href="#/zglos">${icon("flag", 15)}${t("Zgłoś problem", "Report a problem")}</a><span id="ver"></span>`;
  paintPill();
  paintUpdate();
  api.health().then(h => { $("ver").textContent = `eduGO Analiza ${h.version}`; }).catch(() => {});
}

function paintPill() {
  const active = jobs.active;
  const pill = $("jobPill");
  pill.hidden = !active.length;
  if (!active.length) return;
  const running = active.find(j => j.status === "running");
  pill.innerHTML = `<span class="pulse" aria-hidden="true"></span>` + (running
    ? `${t("Analiza", "Analysis")} ${pct(100 * stageProgress(running))}` : t("W kolejce", "Queued")) +
    (active.length > 1 ? ` <small>+${active.length - 1}</small>` : "");
}

// ---- update banner ----
let update = null;
let updateMessage = "";

async function checkUpdate() {
  try { update = await api.update(); } catch (e) { update = null; }
  paintUpdate();
}

function paintUpdate() {
  const bar = $("updBar");
  bar.hidden = !(update && update.available);
  if (bar.hidden) return;
  bar.innerHTML = `<div class="upd-row"><span class="sec-ic">${icon("update", 16)}</span><strong>${t("Dostępna nowa wersja", "A new version is available")} ${esc(update.latest)}</strong>
      <span class="muted">${t("Twoja wersja:", "your version:")} ${esc(update.current)}</span>
      <button class="btn small" id="updBtn" type="button">${icon("update", 16)}${t("Zaktualizuj", "Update")}</button></div>
    <details><summary>${t("Co nowego", "What's new (release notes are in Polish)")}</summary>
      ${update.notes.map(n => `<div class="notes"><b>${esc(n.version)}</b>\n${esc(n.text)}</div>`).join("")}</details>
    <div class="muted" id="updMsg">${esc(tr(updateMessage) || t("Aktualizacja trwa zwykle około minuty. Modele i historia zostaną zachowane.", "Updating usually takes about a minute. Models and history are kept."))}</div>`;
  $("updBtn").onclick = installUpdate;
}

async function installUpdate() {
  $("updBtn").disabled = true;
  try { await api.installUpdate(); } catch (e) { updateMessage = e.message; paintUpdate(); return; }
  const target = update.latest;
  const tick = async () => {
    try {
      const h = await api.health();
      if (h.version === target) { location.reload(); return; }
      const u = await api.update();
      updateMessage = u.message || "Aktualizowanie…";
      if (u.status === "error") { paintUpdate(); return; }
    } catch (e) { updateMessage = "Uruchamianie nowej wersji…"; }
    $("updMsg").textContent = tr(updateMessage);
    setTimeout(tick, 1500);
  };
  tick();
}

// ---- start ----
document.documentElement.lang = LANG;
$("langSw").addEventListener("click", e => {
  const lang = e.target.dataset && e.target.dataset.lang;
  if (lang && lang !== LANG) { setLang(lang); show(); }
});
jobs.subscribe(paintPill);
window.addEventListener("hashchange", show);
show();
jobs.refresh();
checkUpdate();
