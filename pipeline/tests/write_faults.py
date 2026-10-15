"""Record, or stop at, each file write a command makes to claim files.

A writer that stops part-way must leave a state the retry can finish without
losing an edit made in between. ``WriteFaults`` patches the low-level file
operations (``Path.write_text``/``write_bytes``/``open`` for writing/
``unlink``/``rename``/``replace``/``rmdir``, ``os.replace``/``os.rename``/
``os.remove``, ``shutil.copyfile``; the writers under test use no other) and counts the ones that touch ``research/claims`` or
``research/pending`` under the repo root. Run a command once with
``record()`` to list its writes; run it again with ``fail_at(n)`` to raise
``OSError`` in place of write ``n`` (once).

Tests parametrize ``n`` over a module constant and assert the recorded list
has that many entries, so a new write without a stop case fails the
inventory test.
"""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path


class WriteFaults:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.watched = (self.root / "research" / "claims", self.root / "research" / "pending")
        self.writes: list[tuple[str, str]] = []
        self.fail_index: int | None = None
        self.fired = False

    def _rel(self, path) -> str | None:
        try:
            resolved = Path(path).resolve()
        except (TypeError, OSError):
            return None
        for base in self.watched:
            if resolved == base or base in resolved.parents:
                return resolved.relative_to(self.root).as_posix()
        return None

    def _hit(self, kind: str, *paths) -> None:
        rels = [r for r in (self._rel(p) for p in paths) if r is not None]
        if not rels:
            return
        index = len(self.writes)
        self.writes.append((kind, " -> ".join(rels)))
        if self.fail_index is not None and not self.fired and index == self.fail_index:
            self.fired = True
            raise OSError(f"simulated stop at write {index} ({kind} {' -> '.join(rels)})")

    @contextmanager
    def _patched(self):
        import pytest

        mp = pytest.MonkeyPatch()
        real_write_text, real_write_bytes, real_open = Path.write_text, Path.write_bytes, Path.open
        real_unlink, real_rename, real_preplace, real_rmdir = Path.unlink, Path.rename, Path.replace, Path.rmdir
        real_replace, real_os_rename, real_remove = os.replace, os.rename, os.remove
        real_copyfile = shutil.copyfile
        faults = self

        # write_text and write_bytes open the file themselves; that open is the same write.
        inside = {"write": False}

        def write_text(self, *a, **k):
            faults._hit("write", self)
            inside["write"] = True
            try:
                return real_write_text(self, *a, **k)
            finally:
                inside["write"] = False

        def write_bytes(self, *a, **k):
            faults._hit("write", self)
            inside["write"] = True
            try:
                return real_write_bytes(self, *a, **k)
            finally:
                inside["write"] = False

        def p_open(self, mode="r", *a, **k):
            if not inside["write"] and any(flag in mode for flag in "wxa+"):
                faults._hit("write", self)
            return real_open(self, mode, *a, **k)

        def unlink(self, missing_ok=False):
            if self.exists():
                faults._hit("unlink", self)
            return real_unlink(self, missing_ok=missing_ok)

        def p_rename(self, target):
            faults._hit("replace", self, target)
            return real_rename(self, target)

        def p_replace(self, target):
            faults._hit("replace", self, target)
            return real_preplace(self, target)

        def rmdir(self):
            faults._hit("rmdir", self)
            return real_rmdir(self)

        def replace(src, dst, *a, **k):
            faults._hit("replace", src, dst)
            return real_replace(src, dst, *a, **k)

        def os_rename(src, dst, *a, **k):
            faults._hit("replace", src, dst)
            return real_os_rename(src, dst, *a, **k)

        def remove(path, *a, **k):
            faults._hit("unlink", path)
            return real_remove(path, *a, **k)

        def copyfile(src, dst, *a, **k):
            faults._hit("copy", dst)
            return real_copyfile(src, dst, *a, **k)

        mp.setattr(Path, "write_text", write_text)
        mp.setattr(Path, "write_bytes", write_bytes)
        mp.setattr(Path, "open", p_open)
        mp.setattr(Path, "unlink", unlink)
        mp.setattr(Path, "rename", p_rename)
        mp.setattr(Path, "replace", p_replace)
        mp.setattr(Path, "rmdir", rmdir)
        mp.setattr(os, "replace", replace)
        mp.setattr(os, "rename", os_rename)
        mp.setattr(os, "remove", remove)
        mp.setattr(shutil, "copyfile", copyfile)
        try:
            yield self
        finally:
            mp.undo()

    @contextmanager
    def record(self):
        self.writes, self.fail_index, self.fired = [], None, False
        with self._patched():
            yield self

    @contextmanager
    def fail_at(self, index: int):
        self.writes, self.fail_index, self.fired = [], index, False
        with self._patched():
            yield self
