"""Root-level checks for the integrated MovieRec SDLC kit."""
from pathlib import Path
import sys

import yaml
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "movie-rec-agent-starter" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import agentctl  # noqa: E402
from git_preflight import check_allowed_paths  # noqa: E402


def assert_agent_ci_check_name(job_id, job, quality_gates):
    effective_name = job.get("name", job_id)
    expected_names = quality_gates["agent_contract_ci_checks"]
    assert effective_name in expected_names, (
        f"workflow check name {effective_name!r} is not configured in "
        f"agent_contract_ci_checks: {expected_names!r}"
    )
    return effective_name


def test_sdlc_integration_001_registry_from_root():
    tasks = agentctl.load_tasks()
    assert agentctl.ROOT == ROOT
    assert "SDLC-INTEGRATION-001" in tasks
    assert agentctl.validate_tasks(tasks) == []


def test_sdlc_integration_001_workflow_runs_harness():
    workflow = ROOT / ".github" / "workflows" / "agent-contracts.yml"
    config = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert config["name"] == "agent-contracts"
    assert config["on"]["push"]["branches"] == ["main", "feature/**"]
    assert config["on"]["pull_request"]["branches"] == ["main"]
    assert config["permissions"] == {"contents": "read"}

    job_id = "validate-contracts"
    job = config["jobs"][job_id]

    gates = yaml.safe_load(
        (ROOT / "movie-rec-agent-starter/.agents/policies/quality_gates.yaml")
        .read_text(encoding="utf-8")
    )

    ci_reader = yaml.safe_load(
        (ROOT / "movie-rec-agent-starter/.agents/tools/github-ci-reader.yaml")
        .read_text(encoding="utf-8")
    )

    assert gates["agent_contract_ci_checks"] == ["validate-contracts"]
    assert assert_agent_ci_check_name(job_id, job, gates) == "validate-contracts"

    # Product CI must remain separate
    assert gates["product_ci_checks"] == ["test"]

    assert "--required validate-contracts" in ci_reader["commands_examples"][0]
    assert "--required test" in ci_reader["commands_examples"][1]

    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    assert steps[0]["uses"] == "actions/checkout@v4"
    assert steps[1]["uses"] == "actions/setup-python@v5"
    assert steps[1]["with"]["python-version"] == "3.12"

    commands = [step["run"] for step in steps if "run" in step]
    assert commands == [
        "python -m pip install -r requirements-test.txt",
        "python -B movie-rec-agent-starter/scripts/agentctl.py validate",
        "python -B -m unittest discover -s movie-rec-agent-starter/tests/harness -v",
        "python -B -m pytest -q tests/harness/test_integration_001.py",
    ]


def test_agent_ci_check_name_rejects_renamed_job():
    gates = yaml.safe_load(
        (ROOT / "movie-rec-agent-starter/.agents/policies/quality_gates.yaml")
        .read_text(encoding="utf-8")
    )
    job = {"name": "renamed-contract-check"}

    with pytest.raises(AssertionError, match="renamed-contract-check"):
        assert_agent_ci_check_name("validate-contracts", job, gates)


def test_agent_ci_check_name_uses_job_id_without_explicit_name():
    gates = yaml.safe_load(
        (ROOT / "movie-rec-agent-starter/.agents/policies/quality_gates.yaml")
        .read_text(encoding="utf-8")
    )

    assert assert_agent_ci_check_name("validate-contracts", {}, gates) == "validate-contracts"


def test_sdlc_integration_001_allowlist_paths():
    assert check_allowed_paths([".gitignore", "docs/agent/SDLC_INTEGRATION_REPORT.md"], [".gitignore", "docs/"]) == []
    assert check_allowed_paths(["README.md"], ["docs/", ".gitignore"]) == ["README.md"]
    assert check_allowed_paths(["AGENTS.md"], ["AGENTS.md"]) == []
    assert check_allowed_paths([".gitignore"], [".gitignore"]) == []
    assert check_allowed_paths(["AGENTS.md.bak"], ["AGENTS.md"]) == ["AGENTS.md.bak"]
    assert check_allowed_paths([".gitignore.extra"], [".gitignore"]) == [".gitignore.extra"]
    assert check_allowed_paths(["docs-extra/report.md"], ["docs/"]) == ["docs-extra/report.md"]
    assert check_allowed_paths(["../secret.txt"], ["../"]) == ["../secret.txt"]
    assert check_allowed_paths(["/tmp/secret.txt"], ["docs/"]) == ["/tmp/secret.txt"]
    assert check_allowed_paths([r"C:\secret.txt"], ["docs/"]) == [r"C:\secret.txt"]
    assert check_allowed_paths([r"docs\agent\report.md"], ["docs/"]) == []
