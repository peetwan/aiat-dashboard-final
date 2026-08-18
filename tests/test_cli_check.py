from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app import cli


ROOT = Path(__file__).resolve().parents[1]


def test_check_steps_mirror_ci_order():
    steps = cli.check_steps(skip_tests=False)
    assert [name for name, _ in steps] == [
        "compile",
        "validate-pipeline",
        "publication-validate",
        "public-repo-boundary",
        "pytest",
    ]
    commands = dict(steps)
    assert commands["compile"] == [sys.executable, "-m", "compileall", "-q", "app", "explorer", "tools"]
    assert commands["validate-pipeline"] == [sys.executable, "-m", "app.cli", "validate-pipeline"]
    assert commands["publication-validate"] == [sys.executable, "-m", "app.cli", "publication", "validate"]
    assert commands["public-repo-boundary"] == [sys.executable, "tools/validate_public_repo.py"]
    assert commands["pytest"] == [sys.executable, "-m", "pytest", "-q"]
    assert [name for name, _ in cli.check_steps(skip_tests=True)] == [
        "compile",
        "validate-pipeline",
        "publication-validate",
        "public-repo-boundary",
    ]


def test_ci_workflow_runs_the_same_commands_as_check():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "python -m compileall -q app explorer tools" in workflow
    assert "python -m app.cli validate-pipeline" in workflow
    assert "python -m app.cli publication validate" in workflow
    assert "python tools/validate_public_repo.py" in workflow
    assert "python -m pytest -q" in workflow


def test_check_runs_every_step_and_reports_the_failed_one(monkeypatch, capsys):
    executed: list[list[str]] = []

    class FakeCompleted:
        def __init__(self, returncode: int) -> None:
            self.returncode = returncode

    def fake_run(command, cwd):
        assert Path(cwd) == cli.PROJECT_ROOT
        executed.append(command)
        return FakeCompleted(2 if command[-1] == "validate-pipeline" else 0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    exit_code = cli.command_check(argparse.Namespace(skip_tests=False))

    assert exit_code == 1
    assert len(executed) == 5
    summary = json.loads(capsys.readouterr().out.split("== pytest", 1)[1].split("\n", 1)[1])
    assert summary["status"] == "failed"
    assert summary["failed_steps"] == ["validate-pipeline"]


def test_check_passes_when_every_step_passes(monkeypatch, capsys):
    class FakeCompleted:
        returncode = 0

    monkeypatch.setattr(cli.subprocess, "run", lambda command, cwd: FakeCompleted())

    exit_code = cli.command_check(argparse.Namespace(skip_tests=True))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"status": "passed"' in output
    assert "pytest" not in output.split("== public-repo-boundary")[0]
