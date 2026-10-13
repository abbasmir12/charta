"""Sample-data generator for the 3 presets."""
from __future__ import annotations

import argparse
import pathlib
import random


def gen(kind: str, dest: pathlib.Path, n: int = 8) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    made = []
    if kind == "freelancer":
        vendors = ["edf", "free", "sncf", "amazon", "rent"]
        for i in range(n):
            v = random.choice(vendors)
            kind2 = "invoice" if i % 3 == 0 else "receipt"
            p = dest / f"{kind2}_{v}_2026-0{(i % 9) + 1}-15.txt"
            p.write_text(f"{kind2} from {v}\ndate: 2026-0{(i % 9) + 1}-15\ntotal: ${100 + i * 17}.00\n", encoding="utf-8")
            made.append(str(p))
    elif kind == "student":
        for i in range(1, n + 1):
            p = dest / f"lecture_{i:02d}_intro.txt"
            p.write_text(f"Lecture {i}: topic {i}\nKey point: concept {i} explained.\n", encoding="utf-8")
            made.append(str(p))
    else:
        for i in range(n):
            p = dest / f"form_{i + 1:03d}.txt"
            p.write_text(f"name: Person {i}\nphone: 06000000{i:02d}\namount: {50 + i}\n", encoding="utf-8")
            made.append(str(p))
    return made


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", default="all", choices=["all", "freelancer", "student", "data_entry"])
    ap.add_argument("--dest", default="samples")
    ap.add_argument("--n", type=int, default=8)
    a = ap.parse_args()
    kinds = ["freelancer", "student", "data_entry"] if a.kind == "all" else [a.kind]
    for k in kinds:
        print(k, len(gen(k, pathlib.Path(a.dest) / k, a.n)))


if __name__ == "__main__":
    main()
