"""Read the problem-report form's answers (published CSV) and open an issue for each new one.

Each issue body ends with a hidden marker made from the report's time and text, so a report is never filed twice.
"""
import csv
import hashlib
import io
import os
import subprocess
import urllib.request

LABEL = "zgłoszenie"


def gh(*args, data=None):
    return subprocess.run(["gh", *args], input=data, capture_output=True, text=True, check=True).stdout


def file_new_reports(url, repo):
    with urllib.request.urlopen(url, timeout=30) as r:
        rows = list(csv.reader(io.StringIO(r.read().decode("utf-8"))))[1:]   # first row: column names
    known = gh("issue", "list", "--repo", repo, "--label", LABEL, "--state", "all", "--limit", "1000", "--json", "body")
    for row in rows:
        if len(row) < 2 or not row[1].strip():
            continue
        when, text = row[0], row[1].strip()
        marker = "report:" + hashlib.sha1(f"{when}|{text}".encode()).hexdigest()[:12]
        if marker in known:
            continue
        title = "Zgłoszenie: " + " ".join(text.split())[:70]
        body = f"{text}\n\n_Wysłano z programu: {when}_\n\n<!-- {marker} -->"
        print("created", gh("issue", "create", "--repo", repo, "--title", title, "--label", LABEL,
                            "--body-file", "-", data=body).strip())


def main():
    repo = os.environ["REPO"]
    gh("label", "create", LABEL, "--color", "fcbf2c", "--description", "Zgłoszenie z programu", "--force",
       "--repo", repo)
    url = os.environ.get("REPORTS_CSV_URL", "").strip()
    if url:
        file_new_reports(url, repo)
    else:
        print("REPORTS_CSV_URL is not set - no new reports read.")


if __name__ == "__main__":
    main()
