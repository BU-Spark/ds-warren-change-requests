"""Disposable synthetic browser-test workspace. Never opens the real data directory."""

import tempfile
from pathlib import Path

import pymupdf
import uvicorn

from reviewer.api import create_app
from tests.helpers import acme_lines, detail_lines, write_pdf, write_review_pdf
from tests.test_checker import reference_bytes, schedule


def fixtures(destination):
    destination.mkdir(parents=True, exist_ok=True)
    write_pdf(destination / "worker-detail.pdf", detail_lines())
    write_review_pdf(destination / "needs-review.pdf")
    with pymupdf.open(destination / "worker-detail.pdf") as source:
        source[0].get_pixmap(dpi=160).save(destination / "scan.png")
    document = pymupdf.open()
    for page_index in range(5):
        page = document.new_page(width=820, height=600)
        lines = acme_lines()[:3]
        for row_index in range(20):
            rate = "11.00" if page_index == 0 and row_index < 8 else "10.00"
            lines.append(
                (
                    130 + 15 * row_index,
                    [
                        (210, "1 Carpenter at 4 hours"),
                        (380, "4"),
                        (430, rate),
                        (490, "44.00" if rate == "11.00" else "40.00"),
                    ],
                )
            )
        for y, cells in lines:
            for x, text in cells:
                page.insert_text((x, y), text, fontsize=8, fontname="cour")
    document.save(destination / "hundred-rates.pdf")
    document.close()
    (destination / "schedule.csv").write_bytes(reference_bytes())
    (destination / "graph-schedule.csv").write_bytes(
        reference_bytes(
            [
                schedule(position="Bricklayer Journey Person", reg_rate="12.00"),
                schedule(
                    source_csv_row_number="3",
                    position="Bricklayer Foreperson",
                    reg_rate="18.00",
                ),
            ]
        )
    )
    masonry = acme_lines()
    index = 0
    for line_index, (y, cells) in enumerate(masonry):
        if any(x == 430 for x, text in cells) and any(
            x == 210 and "Worker" in text for x, text in cells
        ):
            rate = ["12.00", "18.00", "17.00"][index]
            masonry[line_index] = (
                y,
                [
                    (
                        x,
                        "1 Mason at 4 hours"
                        if x == 210
                        else rate
                        if x == 430
                        else text,
                    )
                    for x, text in cells
                ],
            )
            index += 1
    write_pdf(destination / "masonry.pdf", masonry)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        fixtures(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory(prefix="warren-browser-") as folder:
            data = Path(folder)
            (data / "labor_rates_fa.csv").write_bytes(reference_bytes())
            uvicorn.run(create_app(data), host="127.0.0.1", port=8000)
