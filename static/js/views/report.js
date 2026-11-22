// "Zgłoś problem": an anonymous report, turned into a GitHub issue by the project's workflow.
import { api } from "../api.js";
import { t, tr } from "../i18n.js";
import { icon } from "../icons.js";
import { $, stillHere } from "../ui.js";

export async function render(root) {
  const here = stillHere(root);
  let enabled = false;
  try { enabled = (await api.feedbackEnabled()).enabled; } catch (e) { /* offline */ }
  if (!here()) return;
  root.innerHTML = `
    <div class="topline"><div class="title-block"><h1>${t("Zgłoś problem", "Report a problem")}</h1>
      <div class="muted">${t("Anonimowo – bez konta i bez podpisu.", "Anonymous – no account, no name.")}</div></div></div>
    <section class="card">
      ${enabled ? `
      <label class="lbl" for="fbText">${t("Co się stało? Przy której lekcji i na jakim etapie?", "What happened? With which lesson, at which step?")}</label>
      <textarea id="fbText" rows="6" maxlength="4000"></textarea>
      <p class="warn soft">${t("Zgłoszenie jest publiczne – nie wpisuj imion ani nazwisk, ani linków do nagrań. Wersja programu i informacja o systemie zostaną dołączone automatycznie.",
        "The report is public – do not write students' names, surnames or recording links. The program version and system are added automatically.")}</p>
      <button class="btn" id="fbBtn" type="button">${icon("flag", 16)}${t("Wyślij zgłoszenie", "Send report")}</button> <span class="muted" id="fbMsg"></span>`
      : `<p class="muted">${t("Wysyłanie zgłoszeń nie jest dostępne (brak internetu albo funkcja wyłączona).", "Sending reports is not available (no internet, or the feature is off).")}</p>`}
    </section>`;
  if (!enabled) return;
  $("fbBtn").onclick = async () => {
    $("fbBtn").disabled = true;
    $("fbMsg").textContent = t("Wysyłanie…", "Sending…");
    try {
      await api.sendFeedback($("fbText").value);
      $("fbText").value = "";
      $("fbMsg").textContent = t("Dziękujemy – zgłoszenie wysłane.", "Thank you – the report was sent.");
    } catch (e) { $("fbMsg").textContent = tr(e.message); }
    $("fbBtn").disabled = false;
  };
}
