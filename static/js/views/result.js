// "Wynik": one analysed lesson. Opened from a finished analysis or from the history.
import { api } from "../api.js";
import { t, tr } from "../i18n.js";
import { icon, title } from "../icons.js";
import { bandName, bandOf, bandScale, dec, esc, gauge, minutes, pct, splitBar, stillHere, timelineSvg } from "../ui.js";

const C = { en: "var(--en)", pl: "var(--pl)", teacher: "var(--tea)", students: "var(--stu)" };
const EXTRA_KEYS = ["lesson_min", "small_talk_min", "praise_per_10min", "tech_mentions"];

export async function render(root, id) {
  root.innerHTML = `<p class="muted">${t("Wczytywanie…", "Loading…")}</p>`;
  const here = stillHere(root);
  let item = null, live = null, others = [];
  try { item = await api.historyItem(id); } catch (e) { /* not in the history (yet) */ }
  if (!item) { try { live = await api.job(id); } catch (e) { /* unknown id */ } }
  if (item && item.teacher) {
    try { others = (await api.history()).filter(i => i.teacher === item.teacher && i.id !== id); } catch (e) { /* no average then */ }
  }
  if (!here()) return;
  if (!item && !(live && live.result)) {
    root.innerHTML = `<section class="card empty">${icon("info", 28)}<p>${esc(tr("Nie ma takiej analizy."))}</p>
      <a class="btn2" href="#/historia">${icon("history")}${t("Wróć do historii", "Back to the history")}</a></section>`;
    return;
  }
  paint(root, item || { id, name: live.label || "", result: live.result }, others);
}

/** This teacher's average of each extra metric over their other lessons in the history. */
function teacherAverages(others) {
  const out = { n: others.length };
  for (const k of EXTRA_KEYS) {
    const v = others.map(o => o.extra && o.extra[k]).filter(x => x != null);
    out[k] = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  }
  return out;
}

function paint(root, info, others) {
  const r = info.result, T = r.teacher, S = r.students, L = r.lesson, M = r.methodologist || {}, X = r.extra || {};
  const enAll = (T.en_s || 0) + (S.en_s || 0);
  const avg = teacherAverages(others);
  root.innerHTML = `
    <div class="topline">
      <button class="btn2 small" id="backBtn" type="button">${icon("back", 16)}${t("Wróć", "Back")}</button>
      <div class="title-block">
        <h1>${esc(info.teacher || info.name || t("Wynik analizy", "Analysis result"))}</h1>
        <div class="chips">
          ${info.lesson_date ? `<span class="chip">${icon("history", 13)}${esc(info.lesson_date)}</span>` : ""}
          ${info.kind ? `<span class="chip ${info.kind === "DEMO" ? "demo" : "stale"}">${esc(info.kind)}</span>` : ""}
          ${info.name && info.teacher ? `<span class="chip plain" title="${esc(info.name)}">${esc(info.name)}</span>` : ""}
        </div>
      </div>
      <a class="btn2 small" href="${api.csvUrl(info.id)}" download>${icon("download", 16)}${t("Pobierz CSV", "Download CSV")}</a>
    </div>
    ${warning(L)}

    <div class="grid-hero">
      <section class="card hero">
        ${title("teacher", t("Angielski nauczyciela", "Teacher's English"))}
        <div class="big">${pct(M.teacher_pct)} <small>${t("w skali metodyka", "on the methodologist scale")}</small></div>
        ${bandScale(M.teacher_pct)}
        ${M.teacher_pct == null ? "" : `<p class="muted">${t(`Najbliżej oceny <b>„${esc(bandName(bandOf(M.teacher_pct)))}”</b> z arkusza ocen metodyków.`,
          `Closest to the <b>${esc(bandName(bandOf(M.teacher_pct)))}</b> rating of the methodologists' rating sheet.`)}</p>`}
      </section>
      <section class="card">
        ${title("speech", t("Kto mówi", "Who speaks"))}
        ${splitBar([{ value: L.teacher_talk_pct, color: C.teacher }, { value: L.students_talk_pct, color: C.students }])}
        <div class="legend"><span><i style="background:${C.teacher}"></i>${t("nauczyciel", "teacher")} <b>${pct(L.teacher_talk_pct)}</b></span>
          <span><i style="background:${C.students}"></i>${t("uczniowie", "students")} <b>${pct(L.students_talk_pct)}</b></span></div>
        <div class="gap">${title("english", t("Kto mówi po angielsku", "Who speaks the English"))}</div>
        ${splitBar([{ value: T.en_s, color: C.teacher }, { value: S.en_s, color: C.students }])}
        <div class="legend"><span><i style="background:${C.teacher}"></i>${t("nauczyciel", "teacher")} <b>${pct(enAll ? (100 * T.en_s) / enAll : null)}</b></span>
          <span><i style="background:${C.students}"></i>${t("uczniowie", "students")} <b>${pct(L.students_share_of_english_pct)}</b></span></div>
        <p class="muted">${t("Jaka część angielskiego na lekcji przypada na nauczyciela, a jaka na uczniów.", "Of all the English in the lesson, the share said by the teacher and by the students.")}</p>
      </section>
    </div>

    <section class="card">
      ${title("timeline", t("Przebieg lekcji", "The lesson minute by minute"))}
      <div class="legend">
        <span><i style="background:var(--en)"></i>${t("nauczyciel po angielsku", "teacher in English")}</span>
        <span><i style="background:var(--en2)"></i>${t("uczniowie po angielsku", "students in English")}</span>
        <span><i style="background:var(--pl)"></i>${t("nauczyciel po polsku", "teacher in Polish")}</span>
        <span><i style="background:var(--pl2)"></i>${t("uczniowie po polsku", "students in Polish")}</span>
        ${M.from_minute ? `<span><i class="open-sw"></i>${t("polski początek lekcji", "Polish opening")}</span>` : ""}</div>
      <div class="tl-wrap">${timelineSvg(r.timeline, M.from_minute || 0) || `<p class="muted">${t("Przebieg lekcji niedostępny (analiza wykonana starszą wersją programu).", "No minute-by-minute data (analysis from an older version).")}</p>`}</div>
    </section>

    <section class="card">
      ${title("info", t("Skąd ta liczba?", "Where does this number come from?"))}
      <div class="steps3">
        ${step(pct(T.en_pct), icon("timer", 16) + t("Stoper", "Stopwatch"), t("Tyle czasu, w którym mówił nauczyciel, przypadło na angielski – w całej lekcji.", "The share of the teacher's speaking time in English – over the whole lesson."))}
        ${M.measured_from_turn == null ? step("–", icon("play", 16) + t("Od przejścia na angielski", "From the switch to English"),
          t("Brak danych – analiza wykonana starszą wersją programu.", "Not available – analysis from an older version of the program."))
        : step(pct(M.measured_from_turn), icon("play", 16) + (M.from_minute ? t(`Od ${dec(M.from_minute)} min`, `From minute ${dec(M.from_minute)}`) : t("Cała lekcja", "Whole lesson")),
          M.from_minute ? t("Liczone od chwili, gdy lekcja przeszła głównie na angielski. Polskie powitanie i small talk trwają w każdej lekcji inaczej, dlatego nie są wliczane i nie zaniżają wyniku.",
            "From the moment the lesson switched mainly to English. The Polish greeting and small talk last differently in every lesson, so they don't pull the number down.")
            : t("Lekcja od początku była głównie po angielsku albo w ogóle nie przeszła na angielski – liczona jest w całości.", "The lesson was mostly English from the start, or never switched – it is counted as a whole."))}
        ${step(pct(M.teacher_pct), icon("chart", 16) + t("Skala metodyka", "Methodologist scale"), t("Metodycy oceniają lekcję ze słuchu, a ich oceny są wyższe niż wskazania stopera. Dlatego wynik stopera jest przeliczany na skalę z arkusza ocen.",
          "Methodologists rate a lesson by ear, and their ratings sit higher than a stopwatch. The number is converted to the scale of the rating sheet."))}
      </div>
    </section>

    <div class="grid2">
      <section class="card">
        ${title("chart", t("Dokładny pomiar", "Exact measurement"))}
        <table class="measure">
          <thead><tr><th></th><th>${t("angielski / polski", "English / Polish")}</th><th class="r">${t("angielski", "English")}</th><th class="r">${t("minuty", "minutes")}</th></tr></thead>
          <tbody>
            ${row(icon("analysis", 15) + t("Cała lekcja", "Whole lesson"), L)}
            ${row(icon("teacher", 15) + t("Nauczyciel", "Teacher"), T)}
            ${row(icon("students", 15) + t("Uczniowie", "Students"), S)}
          </tbody>
        </table>
        <p class="muted">${t(`Liczony jest tylko czas, gdy ktoś mówi: <b>${minutes(T.speech_s + S.speech_s)}</b> z ${minutes(r.duration_s)} nagrania.`,
          `Only time when someone speaks is counted: <b>${minutes(T.speech_s + S.speech_s)}</b> of the ${minutes(r.duration_s)} recording.`)}
          ${L.recordings_s > 0 ? t(` Odtwarzane nagrania (np. z podręcznika, filmy – ${minutes(L.recordings_s)}) nie są liczone.`, ` Played recordings (textbook, videos – ${minutes(L.recordings_s)}) are not counted.`) : ""}
          ${t(" Czytanie na głos po angielsku też wlicza się do angielskiego nauczyciela.", " A teacher reading aloud in English counts as the teacher's English.")}</p>
      </section>
      <section class="card">
        ${title("sparkles", t("Wskaźniki dodatkowe", "Extra metrics"), ` <span class="chip plain">${t("eksperymentalne", "experimental")}</span>`)}
        ${X.typical ? `<div class="tiles">
          ${tile("timer", t("Długość lekcji", "Lesson length"), X.lesson_min, `${dec(X.lesson_min)} min`, 50, 70, X.typical.lesson_min, avg.lesson_min, v => `${v}'`)}
          ${tile("speech", t("Polski początek", "Polish opening"), X.small_talk_min, X.small_talk_min == null ? t("brak przejścia na angielski", "no switch to English") : `${dec(X.small_talk_min)} min`, 0, 30, X.typical.small_talk_min, avg.small_talk_min, v => `${v}'`)}
          ${tile("star", t("Pochwały", "Praise"), X.praise_per_10min, `${dec(X.praise_per_10min)} / 10 min`, 0, 25, X.typical.praise_per_10min, avg.praise_per_10min, v => `${v}`)}
          ${tile("wifi", t("Problemy techniczne", "Technical problems"), X.tech_mentions, String(X.tech_mentions), 0, 30, X.typical.tech_mentions, avg.tech_mentions, v => `${v}`)}
        </div>
        <div class="key"><span><i class="k-typ"></i>${t("typowy zakres w lekcjach eduGO (środkowe 50% wyników z lekcji wielu nauczycieli)", "typical for eduGO lessons (the middle half of lessons by many teachers)")}</span>
          <span><i class="k-dot"></i>${t("ta lekcja", "this lesson")}</span>
          ${avg.n ? `<span><i class="k-avg"></i>${t(`średnia tego nauczyciela z Historii (${otherLessonsPl(avg.n)})`, `this teacher's average in History (${avg.n} other ${avg.n === 1 ? "lesson" : "lessons"})`)}</span>` : ""}</div>
        <p class="muted">${t("To wskazówki, nie ocena.", "These are hints, not a rating.")}</p>`
        : `<p class="muted">${t("Niedostępne (analiza wykonana starszą wersją programu).", "Not available (analysis from an older version).")}</p>`}
      </section>
    </div>
    ${info.time ? `<p class="muted center">${t("Analiza z", "Analysed on")} ${esc(info.time)} · ${t("wersja", "version")} ${esc(r.version)}</p>` : ""}`;

  root.querySelector("#backBtn").onclick = () => (history.length > 1 ? history.back() : (location.hash = "#/historia"));
}

const otherLessonsPl = n => `${n} ${n === 1 ? "inna lekcja" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "inne lekcje" : "innych lekcji"}`;

function warning(L) {
  const text = L.roles_doubtful
    ? t("Program nie jest pewien, kto jest nauczycielem – część wypowiedzi uczniów brzmi jak wypowiedzi nauczyciela. Wynik może być mniej dokładny.",
      "The program is not sure who the teacher is – some of the students sound like a teacher. The result may be less accurate.")
    : L.teacher_talk_pct != null && L.teacher_talk_pct < 50
      ? t("Uczniowie mówią tu więcej niż nauczyciel. Tak bywa np. przy pracy w parach albo prezentacjach uczniów.",
        "The students speak more than the teacher here. It happens, e.g. with pair work or student presentations.") : "";
  return text ? `<p class="warn">${icon("alert", 18)}<span>${text}</span></p>` : "";
}

function step(value, label, text) {
  return `<div class="step"><div class="step-v">${value}</div><div class="step-l">${label}</div><p>${text}</p></div>`;
}

function row(label, s) {
  return `<tr><td class="rl">${label}</td><td>${splitBar([{ value: s.en_s, color: C.en }, { value: s.pl_s, color: C.pl }])}</td>
    <td class="r num">${pct(s.en_pct)}</td><td class="r num">${minutes(s.en_s)} / ${minutes(s.pl_s)}</td></tr>`;
}

function tile(iconName, label, value, shown, min, max, typical, teacherAvg, format) {
  const g = gauge({ value, min, max, typical, format, teacherAvg });
  return `<div class="tile"><div class="tile-l">${icon(iconName, 15)}${label}</div><div class="tile-v">${shown}</div>${g.html}<div class="tile-s">${g.verdict}</div></div>`;
}
