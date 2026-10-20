import pathlib

import pytest

from charta.cli import main
from charta.core.demo import MARKER, run, tree


def _files(folder: pathlib.Path) -> set[str]:
    return set(tree(folder))


def test_demo_sorts_freelancer_folder(tmp_path):
    res = run(tmp_path / "demo", "freelancer")
    root = tmp_path / "demo"
    assert res.applied and not res.used_llm
    assert (root / ".charta" / "charter.md").exists()
    assert (root / MARKER).exists()
    assert (root / ".charta" / "outputs" / "receipts.csv").exists()
    assert res.outputs["rows"] == len(res.before)
    # nothing at the flat root, everything in a destination folder
    assert not [p for p in root.iterdir() if p.is_file()]
    assert {"Invoices", "Receipts", "Statements"} <= {p.name for p in root.iterdir()}
    # nothing deleted: every original file still exists somewhere
    assert _files(root) == set(res.after)
    assert len(res.after) == len(res.before)


def test_demo_dry_run_never_moves_or_writes(tmp_path):
    res = run(tmp_path / "demo", "freelancer", apply=False)
    root = tmp_path / "demo"
    assert not res.applied
    assert _files(root) == set(res.before)
    assert not (root / ".charta" / "outputs").exists()


def test_demo_refuses_a_folder_it_did_not_create(tmp_path):
    root = tmp_path / "mine"
    root.mkdir()
    (root / "important.txt").write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run(root, "freelancer")
    assert (root / "important.txt").read_text(encoding="utf-8") == "keep me"


def test_demo_reset_only_rebuilds_its_own_folder(tmp_path):
    root = tmp_path / "demo"
    run(root, "student")
    with pytest.raises(FileExistsError):
        run(root, "student")
    res = run(root, "student", reset=True)
    assert res.applied and len(res.after) == len(res.before)


def test_demo_student_output(tmp_path):
    res = run(tmp_path / "student", "student")
    assert res.applied
    outs = {pathlib.Path(v).name for k, v in res.outputs.items() if isinstance(v, str)}
    assert {"notes.md", "flashcards.csv"} <= outs


def test_demo_data_entry_output(tmp_path):
    res = run(tmp_path / "demo", "data_entry")
    assert res.outputs["rows"] == len(res.before)
    assert pathlib.Path(res.outputs["csv"]).exists()
    assert (tmp_path / "demo" / "Forms").is_dir()


def test_demo_cli_prints_payoff(tmp_path, capsys):
    code = main(["demo", "--folder", str(tmp_path / "demo"), "--preset", "freelancer"])
    out = capsys.readouterr().out
    assert code == 0
    assert "offline heuristic" in out
    assert "Output you did not have to make by hand" in out
    assert "Nothing was deleted" in out
