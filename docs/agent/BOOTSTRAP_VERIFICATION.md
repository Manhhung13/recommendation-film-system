# SDLC-INTEGRATION-001 bootstrap verification

Task/slides: SDLC-INTEGRATION-001 / 2, 10, 11; no task dependencies. Starting HEAD `0dd2453b8b595ff0f1f28172dc7aab41c456b21c`, starting branch `feature/research-readiness-governance`; implementation branch `feature/bootstrap-integration-trust`. Initial tracked worktree/index were clean. Pre-existing untracked `movie-rec-agent-starter/docs/agent/{CURRENT_STATE_AUDIT,GAP_ANALYSIS}.md` remain excluded. Allowed scope is the integration contract: kit scripts/tests and docs only. No data/ML/acquisition changes or raw access.

## Trust boundary and current status

This supplies a verifier, not a signing authority. Native independent agent review can approve code quality; it cannot provision owner trust or substitute for an externally authenticated approval. **Integration remains LOCAL_VERIFIED / NOT VERIFIED and SETUP-001 blocked until the external steps below succeed.** The private key must remain with an independent reviewer/service, never with the author or in this repository. The repository owner must authenticate that reviewer and approve its public-key fingerprint through a separate channel.

An administrator must protect the external trust config/key files with ACLs and lock the verifier runner's environment so task authors cannot replace `MOVIEREC_BOOTSTRAP_TRUST_FILE` or its contents. Merely placing a file outside the checkout does not establish trust. A different account name controlled by the same author is not independent. The local checkout and mutable `.runtime/state.json` are not an authority. Malicious runner administrators, modified verifier code or dishonest externally trusted reviewers are outside this boundary; no trusted deployment is claimed here.

## Process

1. Publish the reviewed bootstrap code to the feature branch. Verify remote SHA/tree and completed `validate-contracts` on that exact SHA. Existing successful CI for `079630c`/`0dd2453b` establishes historical evidence only; it cannot certify this new bootstrap commit. Preserve prior logs/reviews, but do not relabel them as approvals for changed code.
2. A **reviewer-controlled runner** uses the committed verifier to prepare evidence. It directly queries github.com/API over TLS, validates the remote feature ref, commit/tree and actual GitHub commit author, latest exact-SHA successful check, GitHub Actions app ID/slug, workflow path, push event, repository, suite and job/check relationships. It fails on pending/failed/newer attempts and producer/provenance mismatches. Public repositories can use anonymous API access; an optional `GITHUB_TOKEN` stays in that runner's environment, never commands/files/chat.
3. It runs the integration's exact registered AC tests plus the kit unittest harness in an isolated `git archive HEAD` snapshot. Untracked files, raw data and source-user exports are absent. Archive links/traversal are rejected. Test children receive no credentials, trust config, PYTHONPATH/HOME overrides or auto-loaded pytest plugins. Real process exit codes/log hashes are recorded under ignored `.runtime/bootstrap/<SHA>-<time>/`. No state becomes VERIFIED during preparation.
4. The independent reviewer inspects the immutable commit, test execution/provenance and CI, performs actual review, then uses their **external** signing system to approve the complete request. Do not blindly sign author-supplied JSON/logs. Copy only its signed envelope to the checkout. The author cannot approve/sign this request. There is no keygen/sign/force/skip endpoint in this implementation.
5. In the administrator-controlled runner, `finalize` verifies the external approval and fresh live CI, all source/revision fields, named acceptance IDs/commands/exit codes/artifact hashes and a maximum 24-hour UTC validity period. The reviewer must be owner-allowed and differ from the actual commit author's GitHub/email identities. Only then does it preserve the signed checkpoint and automatically transition integration to VERIFIED. A lease prevents concurrent finalizers; retry after a crash is idempotent. A failed verification leaves task state unchanged.
6. `agentctl next`, SETUP `start` and direct/CLI `run-local` revalidate the signed checkpoint and live CI rather than trusting the VERIFIED bit. Changed HEAD/tree/branch, modified tracked sources, changed CI attempts/artifacts, expiry, missing anchor or unsigned receipts block SETUP. Re-run preparation/review as needed. No dataset manifest is required to bootstrap this **infra** task; downstream research manifest/product gates are unchanged.

## Exact external owner actions (required before activation)

The owner chooses a genuinely independent GitHub reviewer or review service, obtains its Ed25519 PEM public key and verifies its SHA-256 fingerprint out of band. An administrator provisions a protected file such as `C:\MovieRecTrust\bootstrap-trust.json` and the protected external public-key PEM. This is **an example shape, not an approved configuration**:

```json
{
  "schema_version": 1,
  "repository": "https://github.com/Manhhung13/recommendation-film-system.git",
  "reviewers": {
    "github:<independent-reviewer-login>": {
      "public_key_file": "C:/MovieRecTrust/independent-reviewer.pem",
      "sha256": "<verified-sha256-of-the-PEM-file-bytes>"
    }
  }
}
```

The independent runner executes from repository root (no private key is supplied to these commands):

```powershell
$env:MOVIEREC_BOOTSTRAP_TRUST_FILE = 'C:\MovieRecTrust\bootstrap-trust.json'
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/bootstrap.py prepare
```

The printed `request.json` is unsigned and cannot authorize anything. The external reviewer preserves all evidence fields, replaces `reviewer_identity` with its owner-approved canonical lowercase identity and `decision` with `APPROVED`, and chooses UTC `issued_at`/`expires_at` covering the actual approval (validity ≤24 hours). Its external signing system emits `{"payload": <approved-request>, "signature": "<base64-Ed25519-signature>"}`. Signature bytes cover `readiness.canonical(payload)`: UTF-8 JSON with sorted keys, compact separators, `ensure_ascii=True`, `allow_nan=False`. Duplicate JSON keys are rejected. The signature certifies actual review and test provenance, not merely a text identity assertion.

Copy the envelope to `.runtime/bootstrap/review-approved.json` and run in the protected runner:

```powershell
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/bootstrap.py finalize --review .runtime/bootstrap/review-approved.json
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/bootstrap.py verify
.\.venv-sdlc\Scripts\python.exe -X utf8 -B movie-rec-agent-starter/scripts/agentctl.py next
```

Only a successful finalizer plus valid checkpoint makes SETUP eligible. Do not hand-edit task YAML/state or reuse the generic research key as an implicitly approved bootstrap reviewer. No owner configuration/signature has been created by this task. Private keys must not be pasted into Codex, committed or stored under `.runtime`.

## Validation and handoff

Changed files: this document, new `movie-rec-agent-starter/scripts/bootstrap.py`, updated `scripts/agentctl.py`, new `tests/harness/test_bootstrap.py`. Tests cover external signature/scope/expiry, self-approval and missing trust rejection, source/remote/CI provenance, artifact integrity, forged state, archive isolation, environment scrubbing, no state changes on rejection, idempotency and one-writer lease. Existing contract/quality policies are unchanged. Actual final tests, independent review, commit/push SHA and exact-SHA CI are reported in the final handoff and ignored `.runtime/evidence/SDLC-INTEGRATION-001/bootstrap-publication.json`; this tracked file is the pre-publication procedure, not a VERIFIED assertion.
