import json
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "soo.pdf"
OUTPUT = ROOT / "tmp" / "pdfs" / "soo_table.json"


def clean_cell(value):
    if value is None:
        return ""
    text = str(value).replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def main():
    with pdfplumber.open(SOURCE) as pdf:
        if not pdf.pages:
            raise RuntimeError("PDF has no pages")
        table = pdf.pages[0].extract_table()

    if not table:
        raise RuntimeError("No table detected in PDF")

    cleaned = [[clean_cell(cell) for cell in row] for row in table]

    # Drop empty trailing columns introduced by PDF table detection.
    while cleaned and all((len(row) == 0 or row[-1] == "") for row in cleaned):
        cleaned = [row[:-1] for row in cleaned]

    max_cols = max(len(row) for row in cleaned)
    normalized = [row + [""] * (max_cols - len(row)) for row in cleaned]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps({"source": SOURCE.name, "rows": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"saved {OUTPUT} rows={len(normalized)} cols={max_cols}")


if __name__ == "__main__":
    main()
