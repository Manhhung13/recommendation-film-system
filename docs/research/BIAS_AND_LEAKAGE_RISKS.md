> SDLC update D-SDLC-2026-10-31: governance clauses below are superseded by
> docs/agent/DEVELOPMENT_SDLC.md. Tests, Git completion receipts, approved business
> decisions and dataset integrity remain required; signatures/review/CI are optional.

# Bias and leakage risks — planning register

All controls require validation; no risk is marked resolved by documentation.

| Risk | Consequence | Proposed control / residual uncertainty |
|---|---|---|
| Rating activity is selected exposure | Rated items differ from unknown/unexposed items | No missing-as-negative labels; disclose observational estimand and coverage |
| Rating time differs from watch time | False sessions/recency interpretation | Name features rating-event recency; tied blocks; no viewing claims |
| MovieLens selected active users | Sparse production users underrepresented | Train-only truncation cohorts, external validity warning; no demographics inferred |
| User/item/popularity confounding | Spurious genre/tag/creator affinities | Shrunk residuals, item/time/popularity controls, paired cohorts; no causal preference claims |
| Full-snapshot Genome/genres/links | Future editorial and community knowledge | Require dated versions for strict mode; enriched sensitivity and explicit uncertainty |
| Current TMDb/IMDb snapshots | Post-cutoff metadata and source-version drift | Hash/version/fetch provenance, available_at evidence, separate modes |
| Popularity/vote/revenue/known-for fields | Future audience outcomes leak into history | Exclude current outcome fields; derive popularity on H(T) |
| Release date/year/region disagreement | False eligibility or negative movie age | Preserve all source values and precision; interval/region policy, quarantine conflicts |
| Vocabulary/normalization/neighbor leakage | Future data enters transforms | Fit all transforms/priors/similarity only on training history |
| Cutoff/cohort/threshold tuning on test | Optimistic reported gains | Development-only cutoff search, approved frozen labels/split, sealed test |
| Sparse support and multiple testing | Unstable affinities and false discoveries | Shrinkage, effective sample sizes, user-cluster intervals, FDR, held-out replication |
| All-pairs interactions/sequences | Scale failure or arbitrary patterns | Pre-register limited feature crosses; bounded neighbors, time windows and count sketches |
| External IDs/many-to-many joins | Duplicated ratings or wrong identity | Only links.csv movie IDs; normalized IMDb tconst; validate cardinality and unresolved IDs |
| Joining user identities | Unsupported identity linkage | Never join MovieLens userId to IMDb/TMDb users or infer identities |
| Missing metadata and language coverage | Coverage mistaken for preference | Explicit masks/denominators; no implicit zero; coverage-stratified sensitivity |
| Crawl 'failed' counted complete | Missing TMDb content hidden by summaries | Check all three durable JSONLs, unique IDs, target scope and approved exclusions |
| Header-only legacy readiness | Malformed content or stale data goes undetected | DATA-QUALITY-001 full semantic tests, immutable manifest; do not rely on database_design_can_start |
| Signer or trust-anchor compromise | Forged tests/review/CI can authorize work | Protected external controller/key/environment; no repo signing key or self-approval; fail closed absent deployment |
| Data changes during hashing/analysis | Manifest/result mismatch | Freeze source snapshot operationally; pre/post stat/hash verification; abort drift |
| User-level reports, raw tags | Privacy and accidental data publication | Untracked restricted outputs, aggregate dashboard and approved small-cell suppression |
| License/provenance uncertainty | Intended usage unsupported | D-08 approval and source-specific retained terms/provenance before use; no new acquisition here |

Residual facts: historical catalog membership and metadata availability may remain unknowable. Strict coverage can be empty; report that outcome. Richer enriched metadata does not resolve historical uncertainty. Recommendations must state coverage/confidence and cannot turn an untested hypothesis into a finding.
