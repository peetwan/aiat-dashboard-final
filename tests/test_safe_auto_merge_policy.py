from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github/workflows/safe-auto-merge.yml"
GITHUB_SCRIPT_V9_SHA = "3a2844b7e9c422d3c10d287c895573f7108da1b3"


def workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_safe_auto_merge_reconciles_every_authorization_changing_event():
    workflow = workflow_text()

    for event in (
        "opened",
        "labeled",
        "unlabeled",
        "synchronize",
        "reopened",
        "ready_for_review",
        "converted_to_draft",
        "edited",
    ):
        assert f"      - {event}\n" in workflow
    assert "github.event.label.name == 'codex-automerge'" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "disablePullRequestAutoMerge" in workflow
    assert "github.rest.issues.removeLabel" in workflow
    assert "['opened', 'synchronize', 'reopened', 'ready_for_review', 'converted_to_draft']" in workflow
    assert "context.payload.changes?.base" in workflow


def test_safe_auto_merge_requires_fresh_peer_authorization_for_main():
    workflow = workflow_text()

    assert "pullRequest.base.ref !== 'main'" in workflow
    assert "context.actor.toLowerCase() === pullRequest.user.login.toLowerCase()" in workflow
    assert "new Set(['admin', 'maintain', 'write'])" in workflow
    assert "const eventHeadSha = context.payload.pull_request.head.sha" in workflow
    assert "pullRequest.head.sha !== eventHeadSha" in workflow
    assert "const authorizedHeadSha = eventHeadSha" in workflow
    assert "pullRequest.head.sha !== authorizedHeadSha" in workflow
    assert workflow.count("await readPullRequest()") >= 3
    assert "github.paginate(github.rest.pulls.listFiles" in workflow
    assert "files.length !== pullRequest.changed_files" in workflow
    assert "file.previous_filename" in workflow
    assert "mergeMethod: SQUASH" in workflow


def test_safe_auto_merge_blocks_critical_policy_and_release_paths():
    workflow = workflow_text()

    for protected_path in (
        "'.github/'",
        "'AGENTS.md'",
        "'SECURITY.md'",
        "'requirements.txt'",
        "'Dockerfile'",
        "'Dockerfile.explorer'",
        "'railway.json'",
        "'railway.explorer.json'",
        "'app/database.py'",
        "'app/models.py'",
        "'app/privacy.py'",
        "'app/ingestion.py'",
        "'app/public_artifacts.py'",
        "'app/publication.py'",
        "'app/cli.py'",
        "'app/server.py'",
        "'app/operations.py'",
        "'explorer/main.py'",
        "'config/'",
        "'data/public/'",
        "'data/spatial/'",
        "'data/demand/'",
        "'tools/build_'",
        "'tools/scaffold_publication.py'",
        "'tools/publication_builders/'",
    ):
        assert protected_path in workflow


def test_safe_auto_merge_uses_pinned_action_and_no_secret_dependent_codex_guess():
    workflow = workflow_text()

    assert (
        f"uses: actions/github-script@{GITHUB_SCRIPT_V9_SHA} # v9"
        in workflow
    )
    assert "actions/github-script@v9" not in workflow
    assert "OPENAI_API_KEY" not in workflow
    assert "openai/codex-action" not in workflow
    assert "codex-bot" not in workflow.lower()
