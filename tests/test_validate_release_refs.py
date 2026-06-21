from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from scripts.release.refs import git_fetch_commit


def test_git_fetch_commit_verifies_exact_commit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    git_fetch_commit("https://github.com/example/repo.git", "a" * 40, tmp_path / "repo")

    assert commands == [
        ["git", "init", "--quiet", str(tmp_path / "repo")],
        [
            "git",
            "-C",
            str(tmp_path / "repo"),
            "remote",
            "add",
            "origin",
            "https://github.com/example/repo.git",
        ],
        ["git", "-C", str(tmp_path / "repo"), "fetch", "--quiet", "--depth=1", "origin", "a" * 40],
        ["git", "-C", str(tmp_path / "repo"), "cat-file", "-e", f"{'a' * 40}^{{commit}}"],
    ]


def test_git_fetch_commit_uses_github_token_header(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr(subprocess, "run", fake_run)

    git_fetch_commit("https://github.com/example/repo.git", "b" * 40, tmp_path / "repo")

    assert commands[2][:4] == [
        "git",
        "-c",
        "http.extraHeader=Authorization: Bearer secret-token",
        "-C",
    ]
