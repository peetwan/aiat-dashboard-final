from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GATE_WORKFLOW_PATH = PROJECT_ROOT / ".github/workflows/publication-gate.yml"
AUTO_MERGE_WORKFLOW_PATH = (
    PROJECT_ROOT / ".github/workflows/publication-auto-merge.yml"
)
CI_WORKFLOW_PATH = PROJECT_ROOT / ".github/workflows/ci.yml"
CHECKOUT_V4_SHA = "11bd71901bbe5b1630ceea73d27597364c9af683"
SETUP_PYTHON_V6_SHA = "a309ff8b426b58ec0e2a45f0f869d46889d02405"
GITHUB_SCRIPT_V9_SHA = "373c709c69115d41ff229c7e5df9f8788daa9553"


def gate_workflow_text() -> str:
    return GATE_WORKFLOW_PATH.read_text(encoding="utf-8")


def auto_merge_workflow_text() -> str:
    return AUTO_MERGE_WORKFLOW_PATH.read_text(encoding="utf-8")


def test_main_pipeline_uses_pinned_actions_and_validates_current_release():
    workflow = CI_WORKFLOW_PATH.read_text(encoding="utf-8")

    assert f"actions/checkout@{CHECKOUT_V4_SHA} # v4.2.2" in workflow
    assert f"actions/setup-python@{SETUP_PYTHON_V6_SHA} # v6.2.0" in workflow
    assert "actions/checkout@v" not in workflow
    assert "actions/setup-python@v" not in workflow
    assert "python -m app.cli publication validate" in workflow


def test_publication_gate_is_always_present_and_read_only_for_pull_requests():
    workflow = gate_workflow_text()

    assert "  pull_request:\n" in workflow
    assert "  pull_request_target:\n" not in workflow
    assert "  publication-gate:\n" in workflow
    assert "    name: publication-gate\n" in workflow
    assert "permissions:\n  contents: read\n" in workflow
    assert "contents: write" not in workflow
    assert "pull-requests: write" not in workflow
    assert "secrets." not in workflow


def test_publication_gate_checks_out_exact_head_and_passes_immutable_revisions():
    workflow = gate_workflow_text()

    assert f"uses: actions/checkout@{CHECKOUT_V4_SHA} # v4.2.2" in workflow
    assert "actions/checkout@v" not in workflow
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert "persist-credentials: false" in workflow
    assert "python .github/scripts/verify_publication.py" in workflow
    assert "--base-sha \"$PUBLICATION_BASE_SHA\"" in workflow
    assert "--head-sha \"$PUBLICATION_HEAD_SHA\"" in workflow
    assert "--report \"$PUBLICATION_REPORT\"" in workflow
    assert "PUBLICATION_BASE_SHA: ${{ github.event.pull_request.base.sha }}" in workflow
    assert "PUBLICATION_HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in workflow


def test_publication_auto_merge_reauthorizes_every_mutating_event_and_main_push():
    workflow = auto_merge_workflow_text()

    assert "  pull_request_target:\n" in workflow
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
    assert "  push:\n    branches:\n      - main\n" in workflow
    assert "context.payload.changes?.base" in workflow
    assert "invalidate-publication-authorizations-on-main-push" in workflow
    assert "disablePullRequestAutoMerge" in workflow
    assert "github.rest.issues.removeLabel" in workflow


def test_publication_auto_merge_requires_peer_review_bound_to_head_and_base():
    workflow = auto_merge_workflow_text()

    assert "      checks: read\n" in workflow
    assert "const authorizationLabel = 'codex-publication-reviewed'" in workflow
    assert "github.event.label.name == 'codex-publication-reviewed'" in workflow
    assert "const eventHeadSha = context.payload.pull_request.head.sha" in workflow
    assert "const eventBaseSha = context.payload.pull_request.base.sha" in workflow
    assert "pullRequest.head.sha !== eventHeadSha" in workflow
    assert "pullRequest.base.sha !== eventBaseSha" in workflow
    assert "function isSameRepository(pullRequest)" in workflow
    assert "!isSameRepository(pullRequest)" in workflow
    assert "fork pull requests require manual review and merge" in workflow
    assert "const authorizedHeadSha = eventHeadSha" in workflow
    assert "const authorizedBaseSha = eventBaseSha" in workflow
    assert "pullRequest.head.sha !== authorizedHeadSha" in workflow
    assert "pullRequest.base.sha !== authorizedBaseSha" in workflow
    assert "pullRequest.base.ref !== 'main'" in workflow
    assert "context.actor.toLowerCase() === pullRequest.user.login.toLowerCase()" in workflow
    assert "new Set(['admin', 'maintain', 'write'])" in workflow
    assert "hasLabel(pullRequest, ordinaryAuthorizationLabel)" in workflow
    assert workflow.count("await readPullRequest()") >= 4
    assert "Pull request changed while auto-merge was being enabled" in workflow
    assert "{ force: true, fail: true }" in workflow
    assert "mergeMethod: SQUASH" in workflow


def test_publication_auto_merge_accepts_only_a_complete_data_public_diff():
    workflow = auto_merge_workflow_text()

    assert "pullRequest.changed_files >= 3000" in workflow
    assert "github.paginate(github.rest.pulls.listFiles" in workflow
    assert "files.length !== pullRequest.changed_files" in workflow
    assert "file.previous_filename" in workflow
    assert "function isStrictPublicDataPath(filename)" in workflow
    assert "parts[0] === 'data'" in workflow
    assert "parts[1] === 'public'" in workflow
    assert "parts.slice(2).every" in workflow
    assert "data/public/serving_manifest.json" in workflow
    assert "Changes to serving_manifest.json require manual review and merge." in workflow


def test_publication_auto_merge_requires_exact_successful_github_actions_checks():
    workflow = auto_merge_workflow_text()

    assert "new Set(['pipeline', 'publication-gate'])" in workflow
    assert "github.rest.checks.listForRef" in workflow
    assert "ref: authorizedHeadSha" in workflow
    assert "checkRun.head_sha === authorizedHeadSha" in workflow
    assert "checkRun.status === 'completed'" in workflow
    assert "checkRun.conclusion === 'success'" in workflow
    assert "checkRun.app?.slug === 'github-actions'" in workflow
    assert "checkPullRequest.number === pullNumber" in workflow
    assert "checkPullRequest.head?.sha === authorizedHeadSha" in workflow
    assert "checkPullRequest.base?.sha === authorizedBaseSha" in workflow


def test_privileged_publication_workflow_never_executes_pull_request_content():
    workflow = auto_merge_workflow_text()

    assert (
        workflow.count(
            f"uses: actions/github-script@{GITHUB_SCRIPT_V9_SHA} # v9"
        )
        == 2
    )
    assert "actions/github-script@v9" not in workflow
    assert "actions/checkout@" not in workflow
    assert "actions/download-artifact@" not in workflow
    assert "downloadArtifact" not in workflow
    assert ".github/scripts/verify_publication.py" not in workflow
    assert "\n        run:" not in workflow
    assert "secrets." not in workflow
