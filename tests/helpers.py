"""Shared synthetic document builders; no client data."""

import pymupdf


def write_pdf(path, lines, *, overlays=()):
    document = pymupdf.open()
    page = document.new_page(width=820, height=600)
    for y, cells in lines:
        for x, text in cells:
            page.insert_text((x, y), text, fontsize=8, fontname="cour")
    for x, y, text, color, font in overlays:
        page.insert_text((x, y), text, fontsize=8, fontname=font, color=color)
    document.save(path)
    document.close()
    return path


def detail_lines():
    headers = list(zip([20, 80, 120, 190, 260, 350, 390, 430, 470, 515, 560, 610, 670, 730],
                       ["Date", "Day", "Ticket", "Name", "Rating", "ST", "OT", "DT", "ST", "OT", "DT", "ST", "OT", "DT"]))
    row = [(20, "01/02/26"), (80, "Fri"), (120, "1000-1001"), (190, "Example"), (250, "Carpenter"),
           (350, "4"), (390, "-"), (430, "-"), (470, "10.00"), (515, "15.00"), (560, "20.00"),
           (610, "40.00"), (670, "-"), (730, "-")]
    second = [(x, "1000-1002" if x == 120 else value) for x, value in row]
    return [(100, headers), (120, row), (140, second)]


def acme_lines():
    return [
        (80, [(20, "LABOR")]),
        (100, list(zip([20, 110, 210, 380, 430, 490, 570, 650],
                      ["DATE", "Quantity", "Description", "HRS", "RATE", "EXTENSION", "OH&P", "TOTAL"]))),
        (115, [(20, "01/02/26")]),
        (130, [(210, "2 Workers at 4 hours"), (380, "8"), (430, "$10.00"), (490, "$80.00"), (570, "$12.00"), (650, "$92.00")]),
        (145, [(210, "1 Worker Premium"), (380, "4"), (430, "$15.00"), (490, "$60.00"), (570, "$9.00"), (650, "$69.00")]),
        (160, [(20, "01/03/26")]),
        (175, [(210, "1 Worker"), (380, "4"), (430, "$10.00"), (490, "$40.00"), (570, "$6.00"), (650, "$46.00")]),
        (195, [(20, "TOTAL LABOR CHARGES"), (380, "16"), (490, "$180.00"), (570, "$27.00"), (650, "$207.00")]),
    ]
