"""scripts/check-release-tag.sh: the site-push rule (OPS-BO, docs/runbook.md § Releasing).

Each test builds a throwaway git repo with the script, a VERSION.md and a roadmap,
then runs the script against HEAD. The repo has no origin, so the script's tag
fetch fails quietly and the local tags decide.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-release-tag.sh"
ROADMAP = "docs/roadmap.md"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class Repo:
    def __init__(self, root: Path):
        self.root = root
        self.rows: list[str] = []
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "test@example.com")
        git(root, "config", "user.name", "Test")
        git(root, "config", "tag.gpgSign", "false")
        git(root, "config", "commit.gpgSign", "false")
        (root / "scripts").mkdir()
        shutil.copy(SCRIPT, root / "scripts" / "check-release-tag.sh")

    def release(self, version: str, changed: list[str]) -> None:
        """Commit the changed files, bump VERSION.md, add the Releases row and tag."""
        for rel in changed:
            write(self.root, rel, f"{version}\n")
        self.rows.append(f"| `{version}` | test | Tagged |")
        write(self.root, "VERSION.md", f"{version}\n\nActive release: {ROADMAP}\n")
        write(self.root, ROADMAP, "| Release | Contents | State |\n|---|---|---|\n" + "\n".join(self.rows) + "\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", version)
        git(self.root, "tag", "-a", f"v{version}", "-m", version)

    def check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "scripts/check-release-tag.sh"],
            cwd=self.root, capture_output=True, text=True,
        )


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    r = Repo(tmp_path)
    r.release("1.0.0-beta.9", ["src/pages/about.astro", "research/claims/a.md"])
    return r


def test_site_push_over_site_files_passes(repo: Repo) -> None:
    repo.release("1.0.0-beta.9.1", ["src/pages/about.astro", "docs/note.md"])
    result = repo.check()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "site push" in result.stdout


@pytest.mark.parametrize("path", [
    "research/claims/a.md",
    "pipeline/x.py",
    "src/pages/research/index.astro",
    "scripts/scheduled-recheck.sh",
    ".github/workflows/recheck.yml",
])
def test_site_push_over_research_change_fails_and_names_the_file(repo: Repo, path: str) -> None:
    repo.release("1.0.0-beta.9.1", ["src/pages/about.astro", path])
    result = repo.check()
    assert result.returncode == 1
    assert path in result.stdout
    assert "site push" in result.stdout
    assert "src/pages/about.astro" not in result.stdout


def test_beta_release_over_research_change_passes(repo: Repo) -> None:
    repo.release("1.0.0-beta.10", ["research/claims/a.md", "pipeline/x.py"])
    result = repo.check()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "beta release" in result.stdout


def test_second_site_push_compares_against_the_first(repo: Repo) -> None:
    repo.release("1.0.0-beta.9.1", ["research/claims/a.md"])
    repo.release("1.0.0-beta.9.2", ["src/pages/values.astro"])
    result = repo.check()
    assert result.returncode == 0, result.stdout + result.stderr


def test_site_push_without_the_tag_it_follows_fails(repo: Repo) -> None:
    repo.release("1.0.0-beta.9.2", ["src/pages/about.astro"])
    result = repo.check()
    assert result.returncode == 1
    assert "v1.0.0-beta.9.1" in result.stdout


def test_untagged_commit_still_fails(repo: Repo) -> None:
    write(repo.root, "src/pages/about.astro", "later\n")
    git(repo.root, "commit", "-qam", "untagged")
    result = repo.check()
    assert result.returncode == 1
    assert "not at the commit being deployed" in result.stdout
