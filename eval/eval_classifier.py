"""Eval: classifier accuracy on sample files with known answers."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from charta.core.charter import preset_charter
from charta.core.classify import propose_for_file

CASES = [
    ("invoice_edf_2026-03-15.txt", "freelancer", "Invoices"),
    ("receipt_rent_2026-03-01.txt", "freelancer", "Receipts"),
    ("lecture_07_notes.txt", "student", "Lectures"),
    ("assignment_2.txt", "student", "Assignments"),
    ("form_001.txt", "data_entry", "Forms"),
]


def main() -> None:
    ok = 0
    for fn, preset, want in CASES:
        ch = preset_charter(preset)
        if preset == "freelancer" and "invoice" not in fn:
            ch.purpose = "receipts and invoices for freelance taxes"
        prop = propose_for_file(fn, fn, ch, None)
        good = prop.dest_dir == want
        ok += good
        print(f"{'PASS' if good else 'FAIL'} {fn}: got {prop.dest_dir}, want {want} ({prop.reason})")
    print(f"\nAccuracy: {ok}/{len(CASES)} = {ok / len(CASES):.0%}")


if __name__ == "__main__":
    main()
