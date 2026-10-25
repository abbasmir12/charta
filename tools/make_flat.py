"""Generate a messy real-world folder: flat paperwork for the demo.

Run:  python tools/make_flat.py --dest <folder>
"""
from __future__ import annotations

import argparse
import pathlib
import zipfile


def _text_pdf(path: pathlib.Path, title: str, lines: list[str]) -> pathlib.Path:
    import fitz  # PyMuPDF
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 90), title, fontsize=17)
    y = 130
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 24
    doc.save(str(path))
    doc.close()
    return path


def _docx(path: pathlib.Path, title: str, body: list[str]) -> pathlib.Path:
    import re

    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    para_xml = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{esc(l)}</w:t></w:r></w:p>" for l in body)
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:body>{para_xml}</w:body></w:document>")
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     "</Types>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
                   ' Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", document)
    return path


def _xlsx(path: pathlib.Path, rows: list[list]) -> pathlib.Path:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "meters"
    for r in rows:
        ws.append(r)
    wb.save(str(path))
    return path


def _write_png(path: pathlib.Path, w: int, h: int, fill) -> pathlib.Path:
    """Minimal PNG writer (RGB) so demo images need no extra dependency."""
    import struct, zlib

    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            r, g, b = fill(x, y)
            raw.extend((r, g, b))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b"")
    path.write_bytes(png)
    return path


def _meter_photo(path: pathlib.Path, kwh: int, month: str) -> pathlib.Path:
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=480, height=260)
    page.insert_text((40, 60), "Compteur electrique", fontsize=12)
    page.insert_text((40, 90), f"lecture kWh: {kwh}", fontsize=16)
    page.insert_text((40, 130), f"periode: {month}", fontsize=11)
    pix = page.get_pixmap(dpi=150)
    path.write_bytes(pix.tobytes("png"))
    doc.close()
    return path


def gen(dest: pathlib.Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    made: list[str] = []

    def put(p: pathlib.Path) -> str:
        made.append(str(p.relative_to(dest)))
        return str(p)

    # Electricity (EDF) -- March is missing on purpose (gap demo)
    for name, lines in [
        ("facture-EDF-janv-2026 (1).pdf", ["Facture EDF - janvier 2026", "Consommation kWh: 02134",
         "echeance: 15/02/2026", "Montant TTC: 79,40 EUR"]),
        ("Scan_0031.pdf", ["Facture EDF - fevrier 2026", "Consommation kWh: 03812",
         "echeance: 16/03/2026", "Montant TTC: 71,20 EUR"]),
        ("new_document(2).pdf", ["Facture EDF - avril 2026", "Consommation kWh: 04711",
         "echeance: 15/05/2026", "Montant TTC: 82,50 EUR"]),
        ("edf_mai_2026.pdf", ["Facture EDF - mai 2026", "Consommation kWh: 05202",
         "echeance: 14/06/2026", "Montant TTC: 88,90 EUR"]),
    ]:
        put(_text_pdf(dest / name, lines[0], lines[1:]))

    put(_meter_photo(dest / "IMG_2401.png", 4711, "mai 2026"))

    # Internet (Orange) -- Feb + May only
    put(_text_pdf(dest / "orange_billing_fev_2026.pdf", "Facturation Orange - fevrier 2026",
                 ["Montant: 24,99 EUR", "date: 2026-02-12"]))
    put(_text_pdf(dest / "orange-billing-may-2026.pdf", "Facturation Orange - mai 2026",
                 ["Montant: 24,99 EUR", "date: 2026-05-20"]))

    # Rent -- lease + 5 monthly receipts (January..May)
    put(_text_pdf(dest / "bail_location_apartment_2025.pdf", "Bail location appartement 2025",
                 ["Location: 705,00 EUR / mois", "Deposit: 1410,00 EUR", "Duree: 12 mois"]))
    for m in ("janv", "fevrier", "mars", "avril", "mai"):
        put(_text_pdf(dest / f"quittance_{m}_2026.pdf", f"Quittance de loyer {m} 2026",
                     ["Montant loyer: 705,00 EUR", "Statut: payee"]))

    # Insurance
    put(_text_pdf(dest / "attestation_MAIF_2026.pdf", "Attestation MAIF 2026",
                 ["Assurance habitation - MAIF", "Prime annuelle: 126,00 EUR",
                  "Echeance: 15/09/2026"]))
    put(_text_pdf(dest / "MAIF_avis_echeance_2026.pdf", "MAIF avis echeance 2026",
                 ["Rappel echeance garantie habitation MAIF"]))

    # Bank
    put(_text_pdf(dest / "confirmations_virement_2026.pdf", "Confirmations virement 2026",
                 ["Virement bail: 705,00 EUR", "Virement electrique: 79,40 EUR"]))
    (dest / "releve_compte_janv-avril.csv").write_text(
        "date,label,amount\n2026-01-05,loyer,-705.00\n2026-02-05,loyer,-705.00\n"
        "2026-02-16,EDF,-79.40\n2026-03-05,loyer,-705.00\n2026-04-05,loyer,-705.00\n"
        "2026-04-16,EDF,-82.50\n2026-05-05,loyer,-705.00\n2026-05-20,Orange,-24.99\n",
        encoding="utf-8")
    made.append("releve_compte_janv-avril.csv")

    # Repairs
    put(_text_pdf(dest / "facture_plomberie_urgent.pdf", "Facture plomberie urgente",
                 ["Fuite salle de bain - intervention du 14/02/2026", "Montant: 240,00 EUR"]))
    put(_text_pdf(dest / "devis_salle_de_bain_scan.pdf", "Devis salle de bain (scan)",
                 ["Devis salle de bain - renovation", "Montant: 1850,00 EUR"]))

    # Warranty
    put(_text_pdf(dest / "garantie_lave_linge_Bosch.pdf", "Garantie lave linge Bosch",
                 ["Garantie 2 ans - lave linge", "Date achat: 02/04/2026",
                  "Reference: LB-2026-8841", "Prix: 189,00 EUR"]))

    # Docs
    put(_docx(dest / "lettre_proprietaire.docx", "Lettre proprietaire",
             ["Madame la proprietaire,", "Suite a la fuite relevee, merci de signer le devis."]))
    (dest / "mail_quotidienne_2026.txt").write_text(
        "From: proprio@exemple.fr\nSubject: travaux\nBody: merci de confirmer le devis.\n",
        encoding="utf-8")
    made.append("mail_quotidienne_2026.txt")
    (dest / "todo_deménagement.md").write_text(
        "# TODO\n- changer l'assurance\n- verifier la chaudiere\n", encoding="utf-8")
    made.append("todo_deménagement.md")
    (dest / "notes_caution.txt").write_text("Depot de garantie: 1410,00 EUR\n", encoding="utf-8")
    made.append("notes_caution.txt")

    # Sensitive document (IBAN + permit number) -> should be flagged sensitive
    put(_text_pdf(dest / "permis_residence_scan.pdf", "Permis de residence 2026",
                 ["Numero permis: X1234567", "IBAN: FR7630004001200500000050"]))

    # Meter readings spreadsheet
    put(_xlsx(dest / "releve_meters_2026.xlsx",
             [["month", "kwh"], ["2026-01", "02134"], ["2026-02", "03812"],
              ["2026-03", None], ["2026-04", "04711"], ["2026-05", "05202"]]))

    # Photos
    _write_png(dest / "IMG_5523.png", 640, 480, lambda x, y: (160, 160, 160))
    made.append("IMG_5523.png")

    return made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="samples/flat-paperwork")
    args = ap.parse_args()
    made = gen(pathlib.Path(args.dest))
    for m in sorted(made):
        print(m)


if __name__ == "__main__":
    main()
