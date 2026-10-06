import os
import subprocess
from pathlib import Path

import pytest

from racn_mcp.git_commit import CommitError, close_theme, commit, git_status


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _current_branch(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit_subjects(repo: Path) -> list[str]:
    result = subprocess.run(
        ["git", "log", "--pretty=%s"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip().splitlines()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def test_commits_staged_changes(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")

    result = commit(location=str(repo), intention="r", risk=".", comment="Add a.txt")

    assert result.message == ". r Add a.txt"
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip() == ". r Add a.txt"


def test_raises_when_nothing_staged(repo: Path):
    with pytest.raises(CommitError, match="No staged changes"):
        commit(location=str(repo), intention="r", risk=".", comment="Nothing to do")


def test_no_staged_changes_error_explains_how_to_fix(repo: Path):
    with pytest.raises(CommitError, match=r"Run `git add` first, or pass `paths`"):
        commit(location=str(repo), intention="r", risk=".", comment="Nothing to do")


def test_raises_for_invalid_location():
    with pytest.raises(CommitError, match="does not exist"):
        commit(location="/does/not/exist", intention="r", risk=".", comment="x")


def test_raises_for_invalid_risk(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")

    with pytest.raises(CommitError, match="Invalid risk"):
        commit(location=str(repo), intention="r", risk="?", comment="x")


def test_raises_for_non_git_directory(tmp_path: Path):
    with pytest.raises(CommitError):
        commit(location=str(tmp_path), intention="r", risk=".", comment="x")


def test_inline_theme_embeds_slug_and_stays_on_current_branch(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")

    result = commit(
        location=str(repo),
        intention="f",
        risk=".",
        comment="Add validation",
        theme_slug="checkout-redesign",
        theme_mode="inline",
    )

    assert result.message == ". f [checkout-redesign] Add validation"
    assert _current_branch(repo) == "master" or _current_branch(repo) == "main"


def test_d_shaped_merge_theme_commits_to_branch_named_after_slug(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")
    commit(location=str(repo), intention="r", risk=".", comment="Initial commit")
    base_branch = _current_branch(repo)

    (repo / "b.txt").write_text("world")
    _git(repo, "add", "b.txt")
    result = commit(
        location=str(repo),
        intention="f",
        risk=".",
        comment="Add b.txt",
        theme_slug="checkout-redesign",
        theme_mode="d_shaped_merge",
    )

    assert result.message == ". f Add b.txt"
    assert _current_branch(repo) == "checkout-redesign"

    (repo / "c.txt").write_text("!")
    _git(repo, "add", "c.txt")
    commit(
        location=str(repo),
        intention="f",
        risk=".",
        comment="Add c.txt",
        theme_slug="checkout-redesign",
        theme_mode="d_shaped_merge",
    )

    assert _current_branch(repo) == "checkout-redesign"
    assert _commit_subjects(repo) == [
        ". f Add c.txt",
        ". f Add b.txt",
        ". r Initial commit",
    ]

    close_theme(location=str(repo), slug="checkout-redesign", target_branch=base_branch)

    assert _current_branch(repo) == base_branch
    subjects = _commit_subjects(repo)
    assert subjects[0] == "checkout-redesign"
    parents = subprocess.run(
        ["git", "rev-list", "--parents", "-1", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert len(parents) == 3  # commit hash + 2 parents


def test_theme_slug_alone_defaults_theme_mode_to_d_shaped_merge(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")
    commit(location=str(repo), intention="r", risk=".", comment="Initial commit")

    (repo / "b.txt").write_text("world")
    _git(repo, "add", "b.txt")
    result = commit(
        location=str(repo),
        intention="f",
        risk=".",
        comment="Add b.txt",
        theme_slug="checkout-redesign",
    )

    assert result.message == ". f Add b.txt"
    assert _current_branch(repo) == "checkout-redesign"


def test_raises_when_theme_mode_given_without_theme_slug(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")

    with pytest.raises(CommitError, match="theme_mode was given without a theme_slug"):
        commit(
            location=str(repo),
            intention="r",
            risk=".",
            comment="x",
            theme_mode="inline",
        )


def test_raises_for_invalid_theme_slug(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")

    with pytest.raises(CommitError, match="Invalid theme slug"):
        commit(
            location=str(repo),
            intention="r",
            risk=".",
            comment="x",
            theme_slug="Not A Slug",
            theme_mode="inline",
        )


def test_close_theme_raises_when_branch_does_not_exist(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")
    commit(location=str(repo), intention="r", risk=".", comment="Initial commit")

    with pytest.raises(CommitError, match="No theme branch"):
        close_theme(
            location=str(repo), slug="nonexistent-theme", target_branch="master"
        )


def test_no_theme_branch_error_explains_how_to_fix(repo: Path):
    (repo / "a.txt").write_text("hello")
    _git(repo, "add", "a.txt")
    commit(location=str(repo), intention="r", risk=".", comment="Initial commit")

    with pytest.raises(CommitError, match="theme_mode='d_shaped_merge'"):
        close_theme(
            location=str(repo), slug="nonexistent-theme", target_branch="master"
        )


def test_close_theme_raises_for_invalid_location():
    with pytest.raises(CommitError, match="does not exist"):
        close_theme(
            location="/does/not/exist", slug="checkout-redesign", target_branch="main"
        )


def test_commit_with_paths_stages_and_commits_without_prior_add(repo: Path):
    (repo / "a.txt").write_text("hello")
    (repo / "b.txt").write_text("world")

    result = commit(
        location=str(repo),
        intention="r",
        risk=".",
        comment="Add a.txt only",
        paths=["a.txt"],
    )

    assert result.message == ". r Add a.txt only"
    status = git_status(str(repo))
    assert "?? b.txt" in status
    assert "a.txt" not in status


def test_commit_with_empty_paths_stages_everything(repo: Path):
    (repo / "a.txt").write_text("hello")
    (repo / "b.txt").write_text("world")

    commit(location=str(repo), intention="r", risk=".", comment="Add both", paths=[])

    assert git_status(str(repo)) == ""


def test_commit_with_paths_dot_stages_everything(repo: Path):
    (repo / "a.txt").write_text("hello")

    commit(
        location=str(repo), intention="r", risk=".", comment="Add a.txt", paths=["."]
    )

    assert git_status(str(repo)) == ""


def test_commit_without_paths_preserves_existing_staged_only_behavior(repo: Path):
    (repo / "a.txt").write_text("hello")
    (repo / "b.txt").write_text("world")
    _git(repo, "add", "a.txt")

    commit(location=str(repo), intention="r", risk=".", comment="Add a.txt")

    status = git_status(str(repo))
    assert "?? b.txt" in status


def test_commit_rejects_paths_escaping_repo_via_dotdot(repo: Path, tmp_path: Path):
    # `repo` and `tmp_path` are the same directory, so an "outside" path must
    # be a sibling of it, not something created underneath it.
    outside = tmp_path.parent / f"{tmp_path.name}_outside.txt"
    outside.write_text("secret")
    try:
        with pytest.raises(CommitError, match="escapes repository root"):
            commit(
                location=str(repo),
                intention="r",
                risk=".",
                comment="x",
                paths=[f"../{outside.name}"],
            )
    finally:
        outside.unlink(missing_ok=True)


def test_path_escape_error_explains_how_to_fix(repo: Path, tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}_outside.txt"
    outside.write_text("secret")
    try:
        with pytest.raises(CommitError, match="must resolve inside the repository"):
            commit(
                location=str(repo),
                intention="r",
                risk=".",
                comment="x",
                paths=[f"../{outside.name}"],
            )
    finally:
        outside.unlink(missing_ok=True)


def test_commit_rejects_absolute_paths_outside_repo(repo: Path, tmp_path: Path):
    outside_dir = tmp_path.parent / f"{tmp_path.name}_outside_repo"
    outside_dir.mkdir()
    outside_file = outside_dir / "outside.txt"
    outside_file.write_text("secret")

    with pytest.raises(CommitError, match="escapes repository root"):
        commit(
            location=str(repo),
            intention="r",
            risk=".",
            comment="x",
            paths=[str(outside_file)],
        )


def test_commit_rejects_symlink_pointing_outside_repo(repo: Path, tmp_path: Path):
    outside_dir = tmp_path.parent / f"{tmp_path.name}_outside_repo"
    outside_dir.mkdir()
    (outside_dir / "outside.txt").write_text("secret")
    link = repo / "link_to_outside"
    try:
        os.symlink(outside_dir, link, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is not permitted in this environment")

    with pytest.raises(CommitError, match="escapes repository root"):
        commit(
            location=str(repo),
            intention="r",
            risk=".",
            comment="x",
            paths=["link_to_outside/outside.txt"],
        )


def test_git_status_shows_untracked_and_staged_changes(repo: Path):
    (repo / "a.txt").write_text("hello")
    (repo / "b.txt").write_text("world")
    _git(repo, "add", "a.txt")

    status = git_status(str(repo))

    assert "A  a.txt" in status
    assert "?? b.txt" in status


def test_git_status_raises_for_invalid_location():
    with pytest.raises(CommitError, match="does not exist"):
        git_status("/does/not/exist")


def test_commit_with_paths_stages_deletion_of_tracked_file(repo: Path):
    (repo / "a.txt").write_text("hello")
    commit(
        location=str(repo),
        intention="r",
        risk=".",
        comment="Add a.txt",
        paths=["a.txt"],
    )
    (repo / "a.txt").unlink()

    commit(
        location=str(repo),
        intention="r",
        risk=".",
        comment="Remove a.txt",
        paths=["a.txt"],
    )

    assert git_status(str(repo)) == ""


def test_commit_rejects_path_that_does_not_exist(repo: Path):
    (repo / "test_tictactoe.py").write_text("hello")

    with pytest.raises(CommitError, match="Path 'tictactoe.py' does not exist"):
        commit(
            location=str(repo),
            intention="r",
            risk=".",
            comment="x",
            paths=["test_tictactoe.py", "tictactoe.py"],
        )
