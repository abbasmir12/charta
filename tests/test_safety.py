import pathlib

import pytest

from charta.core import journal as journal_mod
from charta.core import mover as mover_mod
from charta.core.charter import preset_charter
from charta.core.classify import Proposal, propose_for_file
from charta.core.extract import extract_text
from charta.core.paths import ProtectedPathError, assert_not_protected, is_protected
from charta.core.sensitive import detect
from charta.core.watcher import wait_stable


def test_protected_refusal():
    for p in ("C:\\Windows\\System32", "C:\\Program Files\\x", "/",
              str(pathlib.Path.home())):
        assert is_protected(p), p
        with pytest.raises(ProtectedPathError):
            assert_not_protected(p)


def test_dry_run_moves_nothing(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    ch = preset_charter("student")
    prop = Proposal("a.txt", "Lectures", "a.txt", "test reason", 0.9)
    r = mover_mod.apply_proposal(tmp_path, prop, dry_run=True)
    assert r.dry_run and (tmp_path / "a.txt").exists()
    assert not (tmp_path / "Lectures" / "a.txt").exists()


def test_move_and_undo(tmp_path):
    (tmp_path / "invoice_x.txt").write_text("invoice total $10")
    prop = Proposal("invoice_x.txt", "Invoices", "invoice_x.txt", "moved because test", 0.8)
    mover_mod.apply_proposal(tmp_path, prop)
    assert not (tmp_path / "invoice_x.txt").exists()
    assert (tmp_path / "Invoices" / "invoice_x.txt").exists()
    e = journal_mod.undo_last(tmp_path)
    assert e and (tmp_path / "invoice_x.txt").exists()


def test_no_overwrite_suffix(tmp_path):
    d = tmp_path / "Lectures"
    d.mkdir()
    (d / "a.txt").write_text("old")
    (tmp_path / "a.txt").write_text("new")
    prop = Proposal("a.txt", "Lectures", "a.txt", "reason", 0.5)
    r = mover_mod.apply_proposal(tmp_path, prop)
    assert "(2)" in r.dst and (d / "a.txt").read_text() == "old"


def test_sensitive_detect_and_exclude(tmp_path):
    (tmp_path / "secret.txt").write_text("password: hunter2\ncard 4111 1111 1111 1111")
    rep = detect((tmp_path / "secret.txt").read_text())
    assert rep.sensitive and "password" in rep.kinds or "card" in rep.kinds
    from charta.core.ask import build_index

    idx = build_index(tmp_path, exclude_sensitive=True)
    assert all("secret" not in d["file"] for d in idx)


def test_wait_stable(tmp_path):
    f = tmp_path / "w.txt"
    f.write_text("x")
    assert wait_stable(f, stable_seconds=0.1, poll=0.05)


def test_extract_txt(tmp_path):
    f = tmp_path / "n.txt"
    f.write_text("hello world")
    assert "hello" in extract_text(f).text


def test_reason_logged(tmp_path):
    (tmp_path / "f.txt").write_text("lecture 7 stuff")
    ch = preset_charter("student")
    prop = propose_for_file("lecture_07.txt", "lecture 7", ch, None)
    assert prop.reason and len(prop.reason) > 10


def test_approving_a_file_already_in_place_never_duplicates_it(tmp_path):
    """A re-approved file must not become 'name (2)' — it is already where
    the earlier approval put it (the restart re-scan bug)."""
    import pathlib

    from charta.core import mover as mover_mod
    from charta.core.classify import Proposal

    folder = tmp_path / "f"
    folder.mkdir();(folder / "Bills").mkdir(parents=True)
    (folder / "Bills" / "scan.pdf").write_text("x")
    prop = Proposal(source="Bills/scan.pdf", dest_dir="Bills",
                    new_name="scan.pdf", reason="organise")
    r = mover_mod.apply_proposal(folder, prop)
    assert r.moved is False and "already at its place" in r.reason
    assert not list(folder.rglob("scan (2)*")), "the file duplicated itself"
    assert (folder / "Bills" / "scan.pdf").exists()


def test_a_decided_proposal_is_never_resurrected(tmp_path):
    """Approving or rejecting once is final: a restart-scan must not put
    the same file back into Review as pending again."""
    import pathlib

    from charta.core import proposals as prop_store
    from charta.core.classify import Proposal

    folder = tmp_path / "f2"
    folder.mkdir()
    prop_store.upsert(folder, Proposal(source="scan.pdf", dest_dir="Bills",
                                       new_name="scan.pdf", reason="organise"))
    prop_store.upsert(folder, Proposal(source="scan.pdf", dest_dir="Bills",
                                       new_name="scan.pdf", reason="again",
                                       status="approved"))
    props = prop_store.load_proposals(folder)
    assert len(props) == 1, "the approved proposal must not be duplicated"
    assert props[0].status == "approved", "approval must not be overwritten"


def test_a_renamed_approved_file_is_not_reproposed_after_restart(tmp_path):
    """The restart-scan sees the file under its NEW name; that must not
    re-propose a file an approval already organised."""
    import pathlib

    from charta.core import pipeline, proposals as prop_store
    from charta.core.classify import Proposal

    folder = tmp_path / "f3"
    folder.mkdir();(folder / "Bills").mkdir(parents=True)
    (folder / "Bills" / "efc_renamed.txt").write_text("amount: 10 EUR")
    prop_store.upsert(folder, Proposal(source="efc.txt", dest_dir="Bills/2026",
                                       new_name="efc_renamed.txt",
                                       reason="clearer name", status="approved"))
    seen = pipeline.organized_paths(folder)
    assert "Bills/2026/efc_renamed.txt" in seen
    assert "efc.txt" in seen
    assert "Bills/efc_renamed.txt" not in seen  # only exact targets count
