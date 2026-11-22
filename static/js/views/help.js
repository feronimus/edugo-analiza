// "Instrukcja": the user guide, shown inside the app. The text (both languages) is in static/help.html.
import { t } from "../i18n.js";
import { stillHere } from "../ui.js";

let guide = null;

export async function render(root) {
  const here = stillHere(root);
  if (guide === null) {
    try { guide = await (await fetch("/static/help.html")).text(); } catch (e) { guide = ""; }
  }
  if (!here()) return;
  root.innerHTML = `<div class="topline"><div class="title-block"><h1>${t("Instrukcja", "Instructions")}</h1>
    <div class="muted">${t("Wszystko, co potrafi program.", "Everything the program can do.")}</div></div></div>
    <div class="guide">${guide}</div>`;
  root.querySelectorAll("[data-goto]").forEach(a => {
    a.onclick = e => { e.preventDefault(); const target = root.querySelector(`#${a.dataset.goto}`); if (target) target.scrollIntoView({ behavior: "smooth" }); };
  });
}
