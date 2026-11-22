"""Where things live on disk, and the one-time download of the voice model."""
import json
import os
import urllib.request
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent

# Optional per-computer settings file, e.g. {"data_dir": "D:\\eduGO_data"}. The installer writes it when the
# program folder has Polish letters in its path, because some model libraries can't open such paths.
try:
    _settings = json.loads((APP_DIR / "settings.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    _settings = {}
if _settings.get("data_dir"):
    os.environ.setdefault("EDUGO_DATA", _settings["data_dir"])

DATA_DIR = Path(os.environ.get("EDUGO_DATA", APP_DIR / "data"))
MODELS_DIR = DATA_DIR / "models"
TMP_DIR = DATA_DIR / "tmp"
for _d in (DATA_DIR, MODELS_DIR, TMP_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# The speech models are downloaded from Hugging Face into the data folder too.
os.environ.setdefault("HF_HOME", str(DATA_DIR / "hf"))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

ASR_MODEL = "nemo-parakeet-tdt-0.6b-v3"
SPEAKER_MODEL = MODELS_DIR / "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx"
_SPEAKER_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/"
                + SPEAKER_MODEL.name)


def ensure_models(log=print) -> None:
    """Download the voice model if it isn't there yet. A half-finished download never counts as a model."""
    if not SPEAKER_MODEL.exists():
        log("Pobieranie modelu głosu…")
        part = SPEAKER_MODEL.with_suffix(".part")
        urllib.request.urlretrieve(_SPEAKER_URL, part)
        os.replace(part, SPEAKER_MODEL)
