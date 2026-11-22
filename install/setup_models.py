"""Run once by the installer: download every model, then start the workers once to prove it all works."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from edugo import config  # noqa: E402  (sets the model folders before the model libraries load)


def main():
    print("Folder danych:", config.DATA_DIR)
    config.ensure_models(print)
    import onnx_asr
    print("Pobieranie modelu rozpoznawania mowy (ok. 700 MB, jednorazowo)…")
    onnx_asr.load_model(config.ASR_MODEL, quantization="int8")
    print("Pobieranie modelu wykrywania mowy…")
    onnx_asr.load_vad("silero")
    print("Test działania…")
    from edugo.analyzer import Analyzer
    analyzer = Analyzer(workers=1)
    analyzer.load(print)
    analyzer.close()
    print("OK – modele gotowe.")


if __name__ == "__main__":
    main()
