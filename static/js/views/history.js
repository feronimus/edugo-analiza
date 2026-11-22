// "Historia": earlier analyses on this computer, with filters and the teacher's trend.
import { api } from "../api.js";
import { t, tr } from "../i18n.js";
import { icon, title } from "../icons.js";
import { $, bandOf, esc, lessons, pct, sparkline, stillHere, trendSvg } from "../ui.js";

const filters = { text: "", teacher: "", kind: "", from: "", to: "" };   // kept while the app is open
let items = [];

export async function render(root) {
  root.innerHTML = `<p class="muted">${t("Wczytywanie…", "Loading…")}</p>`;
  const here = stillHere(root);
  let loaded;
  try { loaded = await api.history(); } catch (e) { if (here()) root.innerHTML = `<p class="err">${esc(tr(e.message))}</p>`; return; }
  if (!here()) return;
  items = loaded;
  const teachers = [...new Set(items.map(i => i.teacher).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pl"));
  root.innerHTML = `
    <div class="topline"><div class="title-block"><h1>${t("Historia analiz", "Analysis history")}</h1>
      <div class="muted">${t("Zapisane na tym komputerze – tylko liczby, bez nagrań.", "Kept on this computer – numbers only, no recordings.")}</div></div></div>
    <section class="card filters">
      <div class="input-ic grow">${icon("search")}<input type="search" id="fText" placeholder="${t("Szukaj: nauczyciel, grupa…", "Search: teacher, group…")}" value="${esc(filters.text)}"></div>
      <select id="fTeacher" aria-label="${t("Nauczyciel", "Teacher")}"><option value="">${t("Wszyscy nauczyciele", "All teachers")}</option>
        ${teachers.map(n => `<option ${n === filters.teacher ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>
      <select id="fKind" aria-label="${t("Rodzaj", "Type")}"><option value="">${t("STAŁE i DEMO", "STAŁE and DEMO")}</option>
        ${["STAŁE", "DEMO"].map(k => `<option ${k === filters.kind ? "selected" : ""}>${k}</option>`).join("")}</select>
      <label class="date">${t("od", "from")} <input type="date" id="fFrom" value="${esc(filters.from)}"></label>
      <label class="date">${t("do", "to")} <input type="date" id="fTo" value="${esc(filters.to)}"></label>
      <button class="link" id="fClear" type="button">${icon("close", 14)}${t("Wyczyść", "Clear")}</button>
    </section>
    <div id="trendBox"></div>
    <section class="card"><div class="list-head"><span id="count"></span></div><div id="list" class="hlist"></div></section>`;

  const bind = (id, key, ev = "input") => $(id).addEventListener(ev, e => { filters[key] = e.target.value; paint(); });
  bind("fText", "text"); bind("fTeacher", "teacher", "change"); bind("fKind", "kind", "change");
  bind("fFrom", "from", "change"); bind("fTo", "to", "change");
  $("fClear").onclick = () => { Object.keys(filters).forEach(k => { filters[k] = ""; }); render(root); };
  paint();
}

const dateOf = i => i.lesson_date || i.time.slice(0, 10);
const scaleOf = i => i.teacher_scale ?? i.teacher_en;

function visible() {
  const q = filters.text.toLowerCase();
  return items.filter(i => (!q || `${i.teacher} ${i.name}`.toLowerCase().includes(q))
    && (!filters.teacher || i.teacher === filters.teacher) && (!filters.kind || i.kind === filters.kind)
    && (!filters.from || dateOf(i) >= filters.from) && (!filters.to || dateOf(i) <= filters.to));
}

function paint() {
  const shown = visible();
  $("count").textContent = t(`${shown.length} z ${items.length}`, `${shown.length} of ${items.length}`);
  $("trendBox").innerHTML = filters.teacher ? teacherTrend(shown) : teacherChips();
  $("trendBox").querySelectorAll("[data-teacher]").forEach(b => {
    b.onclick = () => { filters.teacher = b.dataset.teacher; $("fTeacher").value = filters.teacher; paint(); };
  });
  $("list").innerHTML = shown.length ? shown.map(entry).join("")
    : `<div class="empty">${icon(items.length ? "search" : "history", 28)}<p>${items.length ? t("Nic nie pasuje do filtrów.", "Nothing matches the filters.") : t("Brak zapisanych analiz. Wyniki pojawią się tu po pierwszej analizie.", "No analyses yet. Results appear here after the first analysis.")}</p></div>`;
  $("list").querySelectorAll("[data-act]").forEach(b => { b.onclick = e => act(e, b.dataset.act, b.dataset.id); });
}

function teacherChips() {
  const by = {};
  items.forEach(i => { if (i.teacher) (by[i.teacher] = by[i.teacher] || []).push(i); });
  const multi = Object.entries(by).filter(([, l]) => l.length >= 2).sort((a, b) => b[1].length - a[1].length);
  if (!multi.length) return "";
  return `<section class="card">${title("timeline", t("Trend nauczycieli", "Teacher trends"))}<div class="tchips">` +
    multi.map(([name, l]) => {
      const v = l.slice().sort((a, b) => dateOf(a).localeCompare(dateOf(b))).map(scaleOf);
      return `<button class="tchip" type="button" data-teacher="${esc(name)}"><b>${esc(name)}</b><span class="muted">${lessons(l.length)}</span>${sparkline(v)}</button>`;
    }).join("") + `</div></section>`;
}

function teacherTrend(list) {
  const pts = list.slice().sort((a, b) => dateOf(a).localeCompare(dateOf(b)))
    .map(i => ({ value: scaleOf(i), label: `${dateOf(i)} ${i.kind || ""}`, short: dateOf(i).slice(5) }));
  if (!pts.length) return "";
  const avg = pts.reduce((a, p) => a + (p.value || 0), 0) / pts.length;
  return `<section class="card">${title("teacher", `${esc(filters.teacher)} · ${lessons(pts.length)} · ${t("średnio", "average")} ${pct(avg)}`)}
    ${pts.length >= 2 ? trendSvg(pts) : `<p class="muted">${t("Trend pojawi się, gdy będą co najmniej dwie lekcje.", "The trend appears from two lessons.")}</p>`}
    <p class="muted">${t("Angielski nauczyciela w skali metodyka, lekcja po lekcji. Pasy w tle to przedziały z arkusza ocen.", "The teacher's English on the methodologist scale, lesson by lesson. The stripes are the bands of the rating sheet.")}</p></section>`;
}

function entry(i) {
  const v = scaleOf(i), band = v == null ? null : bandOf(v);
  return `<div class="hrow" id="row-${esc(i.id)}">
    <a class="hmain" href="#/wynik/${esc(i.id)}">
      <span class="hdate">${icon("history", 14)}${esc(dateOf(i))}</span>
      <span class="hname"><b>${esc(i.teacher || t("(nieznany nauczyciel)", "(unknown teacher)"))}</b><span class="muted">${esc(i.name)}</span></span>
      ${i.kind ? `<span class="chip ${i.kind === "DEMO" ? "demo" : "stale"}">${esc(i.kind)}</span>` : ""}
      <span class="score" style="--i:${band ? [0, 29, 45, 60, 80, 90].indexOf(band.lo) : 0}">${pct(v)}</span>
    </a>
    <span class="hacts">
      <button class="icon" type="button" data-act="edit" data-id="${esc(i.id)}" title="${t("Zmień nauczyciela (np. przy zastępstwie)", "Correct the teacher (e.g. a substitute)")}">${icon("edit", 16)}</button>
      <button class="icon" type="button" data-act="del" data-id="${esc(i.id)}" title="${t("Usuń z historii", "Delete from history")}">${icon("trash", 16)}</button>
    </span></div>`;
}

async function act(e, action, id) {
  e.preventDefault();
  const row = $(`row-${id}`), item = items.find(i => i.id === id);
  if (action === "edit") {
    row.innerHTML = `<form class="inline" id="ed"><input type="text" id="edName" value="${esc(item.teacher)}" aria-label="${t("Nauczyciel", "Teacher")}">
      <button class="btn small" type="submit">${t("Zapisz", "Save")}</button><button class="btn2 small" type="button" id="edCancel">${t("Anuluj", "Cancel")}</button></form>`;
    $("edName").focus();
    $("edCancel").onclick = paint;
    $("ed").onsubmit = async ev => { ev.preventDefault(); item.teacher = $("edName").value.trim(); await api.setTeacher(id, item.teacher).catch(() => {}); paint(); };
  } else if (action === "del") {
    row.innerHTML = `<div class="inline"><span>${t("Usunąć tę analizę z historii?", "Delete this analysis from the history?")}</span>
      <button class="btn small danger" type="button" id="delYes">${t("Usuń", "Delete")}</button><button class="btn2 small" type="button" id="delNo">${t("Anuluj", "Cancel")}</button></div>`;
    $("delNo").onclick = paint;
    $("delYes").onclick = async () => { await api.deleteItem(id).catch(() => {}); items = items.filter(i => i.id !== id); paint(); };
  }
}
