> SDLC update D-SDLC-2026-10-31: governance clauses below are superseded by
> docs/agent/DEVELOPMENT_SDLC.md. Tests, Git completion receipts, approved business
> decisions and dataset integrity remain required; signatures/review/CI are optional.

# Experiment design — future model tasks only

These are reproducible study specifications. No models or baselines are trained in this planning task, RESEARCH-001 or EDA-001. No empirical metric thresholds are assumed. D-03/D-04/D-05/D-09 and relevant source decisions must be approved before evaluation.

## Common comparison

Use the frozen temporal/catalog protocol in [TEMPORAL_RESEARCH_PROTOCOL.md](TEMPORAL_RESEARCH_PROTOCOL.md). Development determines feature choices; validation tunes; sealed future test evaluates once. Use identical eligible users/items, interacted-item filtering, horizon, labels, candidate pool policy and tie breaking for all methods. Report full-catalog ranking when feasible; sampled evaluation must freeze/disclose the sampler, seed, pool and exclusions. Unrated items are unknown, not negative observations; ranking metrics measure observed positives under selection bias.

Compare Popularity (train-period counts), User/Item CF (bounded sparse neighbors), MF/SVD, Content, Temporal Hybrid and an optional sequence baseline. Popularity/CF/MF/Content are distinct controls; sequence may remain advanced per D-07. Hyperparameter budget, compute limits and temporal validation must be comparable. No global pairwise similarity or test-derived IDF/popularity. Rating prediction RMSE/MAE uses only observed held-out ratings and is reported separately from ranking.

## Ablation matrix

| Variant | Paired control / question |
|---|---|
| raw versus user-centered/shrunk ratings | H01: normalization over each baseline |
| +genres, +tags, +Genome separately | H02/H03: incremental effect and missingness cohorts |
| +year/age, runtime, language, credits separately | H04: source coverage and attribution |
| additive versus limited interactions | H05: nonlinear effect beyond marginal affinities |
| static versus recency/short-long drift | H06: temporal gain versus activity changes |
| shuffled within-history versus ordered sequence | H07: sequence signal beyond recency; respect tied blocks |
| content-only versus +CF/MF signals | H08: collaborative incremental value |
| count popularity versus popularity-stratified controls | H09: head versus tail tradeoff |
| no rerank versus diversity/novelty rerank | H10: accuracy/coverage tradeoff, no inferred exploration intent |
| no shrinkage versus confidence-aware fallback | H11: sparse user/item robustness |
| strict versus enriched; static versus audited as-of | H12: availability sensitivity, never pool modes |

Each row runs on the same frozen data/policies and reports ablation ID, hypothesis IDs, model/config/seed, features removed/added, budget and failure counts. Fit transforms only within the relevant training fold. Interactions must add value over additive terms; control for popularity, history size, time and coverage. Exploratory correlations are not model-quality evidence or causal claims.

## Metrics and uncertainty

For user u, observed eligible future positives P_u and recommendations R_u^K, define Recall@K=`|R∩P|/|P|`, Precision@K=`|R∩P|/K`; disclose short-list policy and realized lengths. NDCG@K=`DCG/IDCG`, with `DCG=sum_{j=1..K} gain(rel_j)/log2(j+1)` and an approved binary or graded gain. Empty-positive users have undefined recall/NDCG: report counts and exclusion policy separately from eligible user coverage. Report macro-user mean and activity-weighted sensitivity; never silently change denominators. K is an approved grid, not automatically 10.

Catalog coverage=`unique recommended eligible items / eligible catalog size`; user coverage=`users served / requested eligible users`. Intra-list diversity=`mean_{i<j}(1-cos(x_i,x_j))`, using documented train-fitted vectors; lists shorter than two yield missing. Novelty=`mean_i -log2((n_i+alpha)/(N+alpha*|I_T|))` with train-only popularity, approved alpha and candidate universe. Report tail coverage and exposure concentration; fresh release is distinct from item novelty. Metrics with zero denominators are missing with reason, never arbitrary zero.

Report paired per-user deltas and 95% user-cluster bootstrap intervals with fixed seeds, plus temporal-block sensitivity for time dependence. Pre-register primary hypotheses/metrics/cohorts and apply Benjamini-Hochberg FDR within the declared H01–H12 exploratory family; report effect sizes, raw/adjusted p values and interval widths. No threshold p alone supports a hypothesis: require reproducible artifacts, practical effect and confounder checks. Suppress tiny cohorts under an approved privacy threshold; do not invent it here.

Cohorts: sparse/warm users, zero-history users/items where observable, history tenure/activity, recent/inactive users, head/mid/tail movies, language/genre and metadata coverage. Define boundaries using training only (D-09); distinguish simulated cold-start from actual zero-history platform users absent from MovieLens. Report failed/missing predictions, compute resources and confidence support, including when intervals are too wide for a conclusion.

## Evidence schema and support decision

Every future result references hypothesis ID, immutable dataset manifest, code SHA, split/cutoff/mode, approved labels, features, cohorts, test/ablation IDs, metric values/denominators, uncertainty, confounder sensitivity and artifact hashes. Report/dashboard totals and IDs must agree. Status progression is UNTESTED → INCONCLUSIVE/SUPPORTED/NOT_SUPPORTED only after empirical execution and independent review; conflicting replications remain visible. All current H01–H12 entries are UNTESTED.
