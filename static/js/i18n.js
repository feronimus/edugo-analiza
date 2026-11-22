// Polish is the app's language; English is there for the people who support it.
import { store } from "./api.js";

export let LANG = store.get("edugo_lang") === "en" ? "en" : "pl";

export function setLang(lang) {
  LANG = lang === "en" ? "en" : "pl";
  store.set("edugo_lang", LANG);
  document.documentElement.lang = LANG;
}

/** Pick the text for the current language: t("Historia", "History"). */
export const t = (pl, en) => (LANG === "en" ? en : pl);

// Messages the program itself sends (progress, errors) are Polish; these are their English versions.
const SERVER = {
  "Pobieranie nagrania z Dropboxa…": "Downloading the recording from Dropbox…",
  "Odczyt ścieżki dźwiękowej…": "Reading the audio track…",
  "Gotowe": "Done",
  "W kolejce…": "Queued…",
  "Wykrywanie mowy…": "Detecting speech…",
  "Wczytywanie modeli…": "Loading models…",
  "Pobieranie modelu głosu…": "Downloading the voice model…",
  "Wystąpił chwilowy problem – ponawiam analizę…": "Temporary problem – retrying the analysis…",
  "Analiza przerwana.": "Analysis cancelled.",
  "Nagranie jest za krótkie.": "The recording is too short.",
  "Nie wykryto mowy w nagraniu.": "No speech was detected in the recording.",
  "Za mało mowy, żeby odróżnić nauczyciela od uczniów.": "Not enough speech to tell the teacher from the students.",
  "To nie jest link do Dropboxa. Wklej link do udostępnionego pliku z Dropboxa (dropbox.com/…).": "This is not a Dropbox link. Paste the link to a shared Dropbox file (dropbox.com/…).",
  "Za mało wolnego miejsca na dysku (potrzeba ok. 1,5 GB). Zwolnij miejsce i spróbuj ponownie.": "Not enough free disk space (about 1.5 GB is needed). Free up some space and try again.",
  "Dropbox nie udostępnia tego pliku (link wygasł, został usunięty albo nie jest publiczny). Sprawdź link w arkuszu.": "Dropbox is not sharing this file (the link expired, was deleted or is not public). Check the link in the spreadsheet.",
  "Dropbox zwrócił stronę zamiast pliku. Sprawdź, czy plik jest udostępniony „każdemu, kto ma link”.": "Dropbox returned a web page instead of the file. Check that the file is shared with “anyone with the link”.",
  "Pobrany plik jest pusty lub uszkodzony.": "The downloaded file is empty or damaged.",
  "Nie da się odczytać pliku nagrania (nieobsługiwany format lub plik uszkodzony).": "The recording cannot be read (unsupported format or damaged file).",
  "Nagranie nie zawiera ścieżki dźwiękowej.": "The recording has no audio track.",
  "Ścieżka dźwiękowa jest pusta.": "The audio track is empty.",
  "Za mało pamięci na tym komputerze. Zamknij inne programy i spróbuj ponownie.": "Not enough memory on this computer. Close other programs and try again.",
  "Nie znaleziono tej analizy (być może program został uruchomiony ponownie).": "This analysis was not found (the program may have been restarted).",
  "Nie ma takiej analizy.": "No such analysis.",
  "Nie ma takiej analizy w historii.": "No such analysis in the history.",
  "Podaj link do nagrania albo wybierz plik.": "Enter a link to the recording or choose a file.",
  "Analiza jeszcze trwa.": "The analysis is still running.",
  "Poczekaj, aż skończą się trwające analizy.": "Wait until the running analyses have finished.",
  "Pobieranie nowej wersji…": "Downloading the new version…",
  "Instalowanie…": "Installing…",
  "Instalowanie dodatkowych składników…": "Installing additional components…",
  "Uruchamianie nowej wersji…": "Starting the new version…",
  "Masz już najnowszą wersję.": "You already have the latest version.",
  "Nie udało się pobrać nowej wersji. Sprawdź połączenie z internetem i spróbuj później.": "Could not download the new version. Check your internet connection and try again later.",
  "Pobrany plik nie jest prawidłową wersją programu eduGO. Aktualizację przerwano.": "The downloaded file is not a valid version of the eduGO program. The update was stopped.",
  "Aktualizacja się nie udała – przywrócono poprzednią wersję.": "The update failed – the previous version was restored.",
  "Aktualizacja się nie udała. Spróbuj później.": "The update failed. Try again later.",
  "Opisz problem w kilku słowach.": "Describe the problem in a few words.",
  "Nie udało się wysłać zgłoszenia. Sprawdź połączenie z internetem i spróbuj ponownie.": "Could not send the report. Check your internet connection and try again.",
  // raised by the page itself
  "Program nie odpowiada. Uruchom „eduGO Analiza” ponownie z pulpitu.": "The program is not responding. Start “eduGO Analiza” again from the desktop.",
  "Program nie odpowiada.": "The program is not responding.",
  "Błąd programu": "Program error",
  "Wklej link do nagrania.": "Paste the link to the recording.",
  "Aktualizowanie…": "Updating…",
};
const SERVER_PATTERNS = [
  [/^Pobieranie nagrania… (\d+) MB(?: z (\d+) MB)?$/, (a, b) => `Downloading the recording… ${a} MB` + (b ? ` of ${b} MB` : "")],
  [/^Problem z połączeniem – ponawiam pobieranie \((\d+)\/(\d+)\)…$/, (a, b) => `Connection problem – retrying the download (${a}/${b})…`],
  [/^Rozpoznawanie mowy i głosów… (\d+)%$/, a => `Recognising speech and voices… ${a}%`],
  [/^Nie udało się pobrać nagrania z Dropboxa – sprawdź połączenie z internetem i link \(([\s\S]*)\)\.$/, e => `Could not download the recording from Dropbox – check your internet connection and the link (${e}).`],
  [/^Nieoczekiwany błąd \(([\s\S]*?)\)\. Spróbuj ponownie – jeśli błąd się powtórzy, uruchom program jeszcze raz\.$/, e => `Unexpected error (${e}). Try again – if it keeps happening, restart the program.`],
  [/^Nie udało się otworzyć folderu: ([\s\S]*)$/, p => `Could not open the folder: ${p}`],
];

/** A message from the program, in the current language (unknown messages are shown as they are). */
export function tr(message) {
  if (LANG !== "en" || message == null) return message;
  const s = String(message);
  if (Object.prototype.hasOwnProperty.call(SERVER, s)) return SERVER[s];
  for (const [re, f] of SERVER_PATTERNS) {
    const m = s.match(re);
    if (m) return f(...m.slice(1));
  }
  return s;
}

// The bands of the methodologists' rating sheet.
export const BANDS = [
  { lo: 0, hi: 29, pl: "Dominacja polskiego", en: "Polish dominates" },
  { lo: 29, hi: 44, pl: "Niewielka", en: "Little English" },
  { lo: 45, hi: 59, pl: "Umiarkowana", en: "Moderate" },
  { lo: 60, hi: 79, pl: "Niezła", en: "Good amount" },
  { lo: 80, hi: 89, pl: "Znaczna", en: "Considerable" },
  { lo: 90, hi: 100, pl: "Dominująca", en: "English dominates" },
];
