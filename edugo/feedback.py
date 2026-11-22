"""Anonymous problem reports.

The text goes to a Google Form, which needs no account and no key. A scheduled GitHub workflow
(.github/workflows/reports.yml) reads the form's answers and turns each one into a GitHub issue.
While FORM_URL is empty the report button is not shown.
"""
from __future__ import annotations

import platform
import urllib.parse
import urllib.request

from . import VERSION, UserError

FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSfsc_XiX5H3AN4OrH_3DMtgv5DGSKqkPjz6dqtsyqQdyXo_Iw/formResponse"
FIELD = "entry.87585233"
MAX_CHARS = 4000


def enabled() -> bool:
    return bool(FORM_URL and FIELD)


def send(text: str) -> None:
    text = text.strip()
    if not text:
        raise UserError("Opisz problem w kilku słowach.")
    body = f"{text[:MAX_CHARS]}\n\n[eduGO {VERSION} · {platform.system()} {platform.release()}]"
    data = urllib.parse.urlencode({FIELD: body}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(FORM_URL, data=data, headers={"User-Agent": "edugo-analiza"}),
                               timeout=15).close()
    except Exception:
        raise UserError("Nie udało się wysłać zgłoszenia. Sprawdź połączenie z internetem i spróbuj ponownie.")
