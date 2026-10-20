import pathlib

from charta.core import journal as journal_mod
from charta.core import proposals as prop_store
from charta.core.charter import preset_charter
from charta.core.pipeline import process_new_file


def test_suggest_mode_only_proposes(tmp_path):
    (tmp_path / "lecture_07.txt").write_text("lecture 7 notes")
    res = process_new_file(tmp_path, tmp_path / "lecture_07.txt", preset_charter("student"))
    assert not res.applied
    assert (tmp_path / "lecture_07.txt").exists()
    props = prop_store.load_proposals(tmp_path)
    assert props and props[0].source == "lecture_07.txt" and props[0].reason


def test_auto_mode_moves_and_journals(tmp_path):
    (tmp_path / "invoice_2026.txt").write_text("invoice total $10")
    res = process_new_file(tmp_path, tmp_path / "invoice_2026.txt",
                           preset_charter("freelancer"), auto_apply=True)
    assert res.applied and res.dst
    assert not (tmp_path / "invoice_2026.txt").exists()
    assert pathlib.Path(tmp_path / res.dst).exists()
    assert journal_mod.entries(tmp_path)
    assert prop_store.load_proposals(tmp_path)[0].status == "approved"


def test_auto_mode_dry_run_moves_nothing(tmp_path):
    (tmp_path / "invoice_2026.txt").write_text("invoice total $10")
    res = process_new_file(tmp_path, tmp_path / "invoice_2026.txt",
                           preset_charter("freelancer"), auto_apply=True, dry_run=True)
    assert not res.applied and res.dst
    assert (tmp_path / "invoice_2026.txt").exists()
    assert not journal_mod.entries(tmp_path)


def test_pipeline_flags_sensitive(tmp_path):
    (tmp_path / "secret.txt").write_text("password: hunter2")
    res = process_new_file(tmp_path, tmp_path / "secret.txt", preset_charter("student"))
    assert res.proposal.sensitive


def test_pipeline_uses_vision_hook(tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"png")
    seen: dict[str, str] = {}

    def vision(data: bytes, mime: str) -> str:
        seen["mime"] = mime
        return "electricity bill for March 2026, total $99"

    res = process_new_file(tmp_path, img, preset_charter("freelancer"), vision=vision)
    assert seen["mime"] == "image/png"
    assert res.proposal.dest_dir


class _Reply:
    def __init__(self, ok: bool, text: str = ""):
        self.ok = ok
        self.text = text


class _StubClient:
    def __init__(self, ok: bool = True):
        self.ok = ok

    def generate(self, *_a, **_k) -> _Reply:
        if not self.ok:
            return _Reply(False, "down")
        return _Reply(True, '{"dest_dir":"ModelDir","new_name":"x.txt",'
                            '"reason":"model reason","confidence":0.91}')


def test_proposal_records_whether_the_model_answered(tmp_path):
    from charta.core.classify import propose_for_file

    ch = preset_charter("student")
    good = propose_for_file("x.txt", "text", ch, _StubClient(True))
    assert good.dest_dir == "ModelDir" and good.origin == "llm"

    down = propose_for_file("x.txt", "text", ch, _StubClient(False))
    assert down.origin == "heuristic" and down.reason
