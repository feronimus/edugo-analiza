// Formatting helpers and the small graphics used on several screens.
import { BANDS, LANG, t } from "./i18n.js";

export const $ = id => document.getElementById(id);

/** Call at the start of an async render; after each await, stop if it returns false (the user moved on). */
export function stillHere(root) {
  const mine = root.dataset.ticket;
  return () => root.dataset.ticket === mine;
}
export const esc = v => String(v ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const dec = v => (LANG === "en" ? String(v) : String(v).replace(".", ","));
export const pct = v => (v == null ? "–" : `${Math.round(v)}%`);
export const minutes = seconds => (seconds == null ? "–" : `${dec((seconds / 60).toFixed(1))} min`);
export const clock = s => { s = Math.round(s); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
export const lessons = n => (LANG === "en" ? `${n} ${n === 1 ? "lesson" : "lessons"}`
  : `${n} ${n === 1 ? "lekcja" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "lekcje" : "lekcji"}`);
export const bandOf = v => BANDS.find(b => v <= b.hi + 0.5) || BANDS[BANDS.length - 1];
export const bandName = b => (LANG === "en" ? b.en : b.pl);

/** A horizontal bar split into coloured parts: [{value, color}]. */
export function splitBar(parts, label) {
  const total = parts.reduce((a, p) => a + (p.value || 0), 0) || 1;
  return `<div class="split" role="img" aria-label="${esc(label || "")}">${parts.map(p =>
    `<div style="width:${(100 * (p.value || 0)) / total}%;background:${p.color}"></div>`).join("")}</div>`;
}

/** The six bands of the rating sheet with a marker at the value. */
export function bandScale(value) {
  const marker = value == null ? "" : `<div class="bs-marker" style="left:${Math.min(100, Math.max(0, value))}%"><span>${pct(value)}</span></div>`;
  return `<div class="bandscale" role="img" aria-label="${esc(t("Skala metodyka", "Methodologist scale"))}">
    <div class="bs-track">${BANDS.map((b, i) => `<div class="bs-seg ${value != null && bandOf(value) === b ? "on" : ""}"
      style="left:${b.lo}%;width:${b.hi - b.lo}%;--i:${i}"></div>`).join("")}${marker}</div>
    <div class="bs-labels">${BANDS.map(b => `<span style="left:${(b.lo + b.hi) / 2}%">${esc(bandName(b))}</span>`).join("")}</div>
  </div>`;
}

/** A value on a track: the typical eduGO range shaded, this lesson as a dot, the teacher's own average as a ▲. */
export function gauge({ value, min, max, typical, format, teacherAvg = null }) {
  const pos = v => `${(100 * (Math.min(max, Math.max(min, v)) - min)) / (max - min)}%`;
  const verdict = value == null ? "" : value < typical[0] ? t("poniżej typowego zakresu", "below the typical range")
    : value > typical[1] ? t("powyżej typowego zakresu", "above the typical range") : t("w typowym zakresie", "in the typical range");
  const html = `<div class="gauge"><div class="g-typ" style="left:${pos(typical[0])};right:calc(100% - ${pos(typical[1])})"></div>
    ${teacherAvg == null ? "" : `<div class="g-avg" style="left:${pos(teacherAvg)}" title="${esc(t("średnia tego nauczyciela", "this teacher's average"))}: ${esc(dec(Math.round(teacherAvg * 10) / 10))}"></div>`}
    ${value == null ? "" : `<div class="g-dot" style="left:${pos(value)}"></div>`}</div>
    <div class="g-scale"><span>${format(min)}</span><span>${format(max)}</span></div>`;
  return { html, verdict };
}

/** Minute-by-minute course of the lesson: English above the line, Polish below; teacher dark, students light. */
export function timelineSvg(minutesData, fromMinute) {
  if (!minutesData || !minutesData.length) return "";
  const n = minutesData.length, W = 10, H = 60, h = 120, pad = 18;
  const width = n * W, y0 = pad + h / 2;
  const scale = s => (Math.min(60, s) / 60) * (h / 2);
  let bars = "";
  minutesData.forEach(([te, tp, se, sp], i) => {
    const x = i * W + 1, w = W - 2;
    const tip = t(`${i + 1}. min – nauczyciel: ${Math.round(te)} s ang., ${Math.round(tp)} s pol.; uczniowie: ${Math.round(se)} s ang., ${Math.round(sp)} s pol.`,
      `minute ${i} – teacher: ${Math.round(te)} s English, ${Math.round(tp)} s Polish; students: ${Math.round(se)} s English, ${Math.round(sp)} s Polish`);
    bars += `<g><title>${esc(tip)}</title>
      <rect x="${x}" y="${y0 - scale(te)}" width="${w}" height="${scale(te)}" class="tl-te"/>
      <rect x="${x}" y="${y0 - scale(te) - scale(se)}" width="${w}" height="${scale(se)}" class="tl-se"/>
      <rect x="${x}" y="${y0}" width="${w}" height="${scale(tp)}" class="tl-tp"/>
      <rect x="${x}" y="${y0 + scale(tp)}" width="${w}" height="${scale(sp)}" class="tl-sp"/></g>`;
  });
  const opening = fromMinute > 0 ? `<rect x="0" y="${pad - 4}" width="${fromMinute * W}" height="${h + 8}" rx="4" class="tl-open"/>` : "";
  let ticks = "";
  for (let m = 0; m <= n; m += 10) ticks += `<text x="${Math.min(width - 6, m * W)}" y="${y0 + h / 2 + 14}" class="tl-tick" text-anchor="${m === 0 ? "start" : "middle"}">${m}'</text>`;
  return `<svg class="timeline" viewBox="0 -4 ${width} ${h + pad + 22}" role="img"
      aria-label="${esc(t("Przebieg lekcji minuta po minucie", "The lesson minute by minute"))}">
    ${opening}${bars}<line x1="0" x2="${width}" y1="${y0}" y2="${y0}" class="tl-axis"/>
    <text x="2" y="${pad + 8}" class="tl-side">${esc(t("angielski", "English"))} ↑</text>
    <text x="2" y="${y0 + h / 2 - 4}" class="tl-side">${esc(t("polski", "Polish"))} ↓</text>${ticks}</svg>`;
}

/** Line chart of the teacher's English (methodologist scale) across lessons, over the band stripes. */
export function trendSvg(points) {
  const W = 600, H = 180, L = 34, R = 10, T = 10, B = 26;
  const x = i => L + (points.length < 2 ? (W - L - R) / 2 : (i * (W - L - R)) / (points.length - 1));
  const y = v => T + (H - T - B) * (1 - v / 100);
  const stripes = BANDS.map((b, i) => `<rect x="${L}" y="${y(b.hi)}" width="${W - L - R}" height="${y(b.lo) - y(b.hi)}" class="tr-band" style="--i:${i}"/>
    <text x="${L - 4}" y="${y((b.lo + b.hi) / 2) + 4}" class="tr-axis" text-anchor="end">${b.lo}</text>`).join("");
  const line = points.map((p, i) => `${x(i)},${y(p.value)}`).join(" ");
  const dots = points.map((p, i) => `<g><title>${esc(`${p.label}: ${pct(p.value)}`)}</title><circle cx="${x(i)}" cy="${y(p.value)}" r="5" class="tr-dot"/></g>
    <text x="${x(i)}" y="${H - 8}" class="tr-axis" text-anchor="middle">${esc(p.short)}</text>`).join("");
  return `<svg class="trend" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Trend nauczyciela", "Teacher trend"))}">
    ${stripes}<polyline points="${line}" class="tr-line"/>${dots}</svg>`;
}

export function sparkline(values) {
  const w = 90, h = 24;
  const pts = values.map((v, i) => `${(values.length < 2 ? w / 2 : (i * w) / (values.length - 1)).toFixed(1)},${(h - 2 - ((v ?? 0) / 100) * (h - 4)).toFixed(1)}`).join(" ");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="var(--en)" stroke-width="2" stroke-linejoin="round"/></svg>`;
}

let toastTimer = null;
/** A short message in the corner, optionally with a link: toast("Gotowe", {href, label}). */
export function toast(message, link) {
  const box = $("toast");
  box.innerHTML = `<span>${esc(message)}</span>${link ? `<a href="${esc(link.href)}">${esc(link.label)}</a>` : ""}`;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, link ? 12000 : 5000);
}
