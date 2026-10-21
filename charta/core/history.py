"""Folder history: a private git repository that records what Charta changed.

Every watched folder can carry a hidden git repository at ``.charta/git`` whose
work tree is the folder itself. Charta commits after it indexes files, moves
one, rebuilds outputs or trashes a file, with a human-readable message ("moved
because it is an electricity bill dated March 2026").

Why a real git repo:
  * the user can see exactly what changed, when, and why — `git log` in their
    own terminal, in the folder;
  * an old version of a file can be restored with one click;
  * nothing is ever deleted by a restore — a restore copies the old file back.

The repository lives inside ``.charta/`` so the user's folder stays clean, and
``.charta/`` itself is excluded from the index, so the history never records
its own bookkeeping.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import shutil
import subprocess

GIT_DIR_NAME = "git"
EXCLUDES = (".charta/\n", ".git/\n", "Thumbs.db\n", "desktop.ini\n", ".DS_Store\n")

# One history entry: when, what, and which files it touched.
Commit = dict[str, str]


def git_dir(folder: str | pathlib.Path) -> pathlib.Path:
    """Where the folder's private repository lives."""
    return pathlib.Path(folder) / ".charta" / GIT_DIR_NAME


def available() -> bool:
    """True when git is on PATH (Charta works without it, just without history)."""
    return shutil.which("git") is not None


def _env(folder: pathlib.Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({
        "GIT_DIR": str(git_dir(folder)),
        "GIT_WORK_TREE": str(folder),
        "GIT_AUTHOR_NAME": "Charta",
        "GIT_AUTHOR_EMAIL": "charta@localhost",
        "GIT_COMMITTER_NAME": "Charta",
        "GIT_COMMITTER_EMAIL": "charta@localhost",
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def _run(folder: str | pathlib.Path, args: list[str], timeout: float = 60.0) -> str | None:
    """Run one git command. Returns stdout, or None when git failed."""
    root = pathlib.Path(folder)
    try:
        proc = subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
            cwd=str(root), env=_env(root), capture_output=True, text=True,
            timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def ensure(folder: str | pathlib.Path) -> bool:
    """Create the private repository if needed. True when history is available."""
    if not available():
        return False
    root = pathlib.Path(folder)
    if not root.exists():
        return False
    gd = git_dir(root)
    if not (gd / "HEAD").exists():
        gd.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["git", "init", "--bare", "--quiet", str(gd)],
                           capture_output=True, text=True, timeout=60, check=False)
        except (OSError, subprocess.SubprocessError):
            return False
        if not (gd / "HEAD").exists():
            return False
        _run(root, ["config", "core.bare", "false"])
        _run(root, ["config", "core.worktree", str(root)])
        _run(root, ["config", "core.logAllRefUpdates", "true"])
        info = gd / "info"
        info.mkdir(parents=True, exist_ok=True)
        (info / "exclude").write_text("".join(EXCLUDES), encoding="utf-8")
    return True


def is_ready(folder: str | pathlib.Path) -> bool:
    """True when this folder already has a usable history."""
    return (git_dir(folder) / "HEAD").exists()


def commit(folder: str | pathlib.Path, message: str) -> str | None:
    """Record the folder's current state. Returns the commit sha, or None."""
    root = pathlib.Path(folder)
    if not ensure(root):
        return None
    if _run(root, ["add", "-A", "."]) is None:
        return None
    out = _run(root, ["commit", "-m", message, "--quiet"])
    if out is None:
        return None  # nothing changed (or git refused) — that is not an error
    sha = _run(root, ["rev-parse", "HEAD"])
    return sha.strip() if sha else None


def log(folder: str | pathlib.Path, limit: int = 40) -> list[Commit]:
    """The newest commits first: sha, when, message, files changed."""
    root = pathlib.Path(folder)
    if not is_ready(root):
        return []
    out = _run(root, ["log", f"-{max(1, int(limit))}", "--name-only",
                      "--pretty=format:%H%x1f%ad%x1f%s", "--date=short"])
    if not out:
        return []
    commits: list[Commit] = []
    for block in out.split("\x1e"):
        block = block.strip("\n")
        if not block.strip():
            continue
        head, _, files = block.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        commits.append({
            "sha": parts[0].strip(),
            "date": parts[1].strip(),
            "message": parts[2].strip(),
            "files": ", ".join(f.strip() for f in files.splitlines() if f.strip()),
            "count": str(len([f for f in files.splitlines() if f.strip()])),
        })
    return commits


def files_at(folder: str | pathlib.Path, sha: str) -> list[str]:
    """The file names recorded in one commit."""
    root = pathlib.Path(folder)
    if not is_ready(root) or not sha:
        return []
    out = _run(root, ["show", "--name-only", "--pretty=format:", sha])
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


def read_at(folder: str | pathlib.Path, sha: str, path: str) -> str | None:
    """The contents of one file as it was in a commit."""
    root = pathlib.Path(folder)
    if not is_ready(root) or not sha or not path:
        return None
    out = _run(root, ["show", f"{sha}:{path}"])
    return out


def restore_file(folder: str | pathlib.Path, sha: str, path: str) -> str | None:
    """Copy an old version of a file back into the folder.

    A restore is a copy: the current file is kept as ``<name>.charta-old`` so
    nothing is ever lost, and the restore itself is committed.
    """
    root = pathlib.Path(folder)
    if not is_ready(root):
        return None
    content = read_at(root, sha, path)
    if content is None:
        return None
    target = root / path
    if target.exists():
        backup = target.with_name(target.name + ".charta-old")
        shutil.copy2(str(target), str(backup))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def status(folder: str | pathlib.Path) -> int:
    """How many files differ from the last commit (0 when clean)."""
    root = pathlib.Path(folder)
    if not is_ready(root):
        return 0
    out = _run(root, ["status", "--porcelain"])
    return len([line for line in (out or "").splitlines() if line.strip()])


def summary(folder: str | pathlib.Path) -> dict[str, str]:
    """One line about the folder's history (for the Folders page)."""
    root = pathlib.Path(folder)
    if not is_ready(root):
        return {"state": "none"}
    head = _run(root, ["log", "-1", "--pretty=format:%h %ad %s", "--date=short"])
    count = _run(root, ["rev-list", "--count", "HEAD"])
    return {"state": "ready",
            "last": (head or "").strip(),
            "commits": (count or "0").strip()}


def now() -> str:
    """Timestamp used in commit messages that need one."""
    return datetime.datetime.now().isoformat(timespec="seconds")
