// "Ustawienia": choices remembered on this computer, updates and the data folder.
import { api, store } from "../api.js";
import { LANG, setLang, t, tr } from "../i18n.js";
import { icon, title } from "../icons.js";
import { $ } from "../ui.js";

const MODES = [["full", "Pełna moc", "Full power", "najszybciej", "fastest"],
  ["balanced", "Zostaw 1 rdzeń wolny", "Leave 1 core free", "zalecane", "recommended"],
  ["light", "Zostaw 2 rdzenie wolne", "Leave 2 cores free", "możesz w tym czasie swobodnie pracować", "you can work alongside"]];

export async function render(root) {
  const mode = store.get("edugo_mode") || "balanced";
  const autoOpen = store.get("edugo_autoopen") !== "0";
  root.innerHTML = `
    <div class="topline"><div class="title-block"><h1>${t("Ustawienia", "Settings")}</h1>
      <div class="muted">${t("Zapamiętane na tym komputerze.", "Remembered on this computer.")}</div></div></div>
    <section class="card setting">
      ${title("globe", t("Język", "Language"))}
      <div class="seg" role="group">${[["pl", "Polski"], ["en", "English"]].map(([l, n]) =>
        `<button type="button" data-choose="${l}" aria-pressed="${l === LANG}">${n}</button>`).join("")}</div>
    </section>
    <section class="card setting">
      ${title("cpu", t("Moc komputera podczas analizy", "Computer power during an analysis"))}
      <div class="cards3">${MODES.map(([v, pl, en, pls, ens]) => `<label class="opt"><input type="radio" name="mode" value="${v}" ${v === mode ? "checked" : ""}>
        <span><b>${t(pl, en)}</b><small>${t(pls, ens)}</small></span></label>`).join("")}</div>
      <p class="muted">${t("Wynik jest zawsze taki sam – zmienia się tylko czas analizy.", "The result is always the same – only the analysis time changes.")}</p>
    </section>
    <section class="card setting">
      ${title("bell", t("Po zakończeniu analizy", "When an analysis finishes"))}
      <label class="toggle"><input type="checkbox" id="autoOpen" ${autoOpen ? "checked" : ""}>
        <span>${t("Otwieraj wynik automatycznie (gdy jestem w zakładce Analiza)", "Open the result automatically (when I'm on the Analysis page)")}</span></label>
    </section>
    <section class="card setting">
      ${title("update", t("Aktualizacje", "Updates"))}
      <p>${t("Przy każdym uruchomieniu program sprawdza, czy jest nowa wersja, i jeśli jest – pokazuje żółtą ramkę u góry.", "The program checks for new versions at every start and shows a yellow banner at the top.")}</p>
      <button class="btn2" id="checkBtn" type="button">${icon("refresh", 16)}${t("Sprawdź teraz", "Check now")}</button> <span class="muted" id="checkMsg"></span>
    </section>
    <section class="card setting">
      ${title("folder", t("Dane", "Data"))}
      <p>${t("Historia, modele i dziennik programu są w podfolderze <code>data</code> w folderze programu.", "History, models and the program log are in the <code>data</code> folder next to the program.")}</p>
      <button class="btn2" id="dataBtn" type="button">${icon("folder", 16)}${t("Otwórz folder z danymi", "Open the data folder")}</button> <span class="muted" id="dataMsg"></span>
    </section>`;

  root.querySelectorAll(".seg [data-choose]").forEach(b => { b.onclick = () => { setLang(b.dataset.choose); window.dispatchEvent(new HashChangeEvent("hashchange")); }; });
  root.querySelectorAll("input[name=mode]").forEach(r => { r.onchange = () => store.set("edugo_mode", r.value); });
  $("autoOpen").onchange = e => store.set("edugo_autoopen", e.target.checked ? "1" : "0");
  $("checkBtn").onclick = async () => {
    $("checkMsg").textContent = t("Sprawdzanie…", "Checking…");
    try {
      const u = await api.update(true);
      $("checkMsg").textContent = u.available ? t(`Dostępna jest wersja ${u.latest} – kliknij „Zaktualizuj” u góry.`, `Version ${u.latest} is available – click “Update” at the top.`)
        : t(`Masz najnowszą wersję (${u.current}).`, `You have the latest version (${u.current}).`);
      if (u.available) location.reload();
    } catch (e) { $("checkMsg").textContent = tr(e.message); }
  };
  $("dataBtn").onclick = async () => {
    try { const r = await api.openData(); $("dataMsg").textContent = r.path || ""; } catch (e) { $("dataMsg").textContent = tr(e.message); }
  };
}
