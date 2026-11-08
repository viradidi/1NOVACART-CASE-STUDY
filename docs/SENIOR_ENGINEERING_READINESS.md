# NovaCart Senior Engineering Readiness Review

**Review date:** 8 November 2026  
**Repository:** [viradidi/1NOVACART-CASE-STUDY](https://github.com/viradidi/1NOVACART-CASE-STUDY)  
**Reviewed branch:** `main`  
**Reviewed commit:** `2f5d6283aac4006f4628259dc133fc4a6df3bb10`  
**Portfolio assessment:** **8.8/10**

## Executive assessment

NovaCart is a strong end-to-end data engineering case study with meaningful implementation depth. It goes beyond a simple medallion notebook demonstration: the repository preserves timestamp-and-key incremental ingestion, Bronze and Silver processing control, deterministic data-quality handling, shared Spark transformations, order-grain Gold modeling, payment-grain health metrics, SCD Type 2 history, impacted-category refresh logic, snapshots, job configuration, dashboard definitions, tests, and a repeatable release package.

The project owner confirmed that NovaCart ran successfully end to end in their Azure Databricks environment on **5 November 2026**. The original cloud environment was later decommissioned to control cost. The exact deployed commit and detailed run artifacts were not supplied to this repository, so this review records the run as owner-confirmed and does not represent it as independently inspectable cloud evidence.

The **8.8/10** score is a portfolio-engineering assessment of the preserved implementation, tests, and documentation. It is not a production certification, a claim of continuous hosting, or proof that every edge-case scenario in the validation plan has been exercised.

## Capability assessment

| Area | Assessment | Reason |
|---|---:|---|
| Architecture and separation of concerns | 9.0/10 | Bronze, Silver, and Gold roles are clear; shared transformation logic is separated from notebook orchestration |
| Incremental processing and correctness | 8.8/10 | Composite timestamp/key cursor, per-entity control state, replay-aware writes, and explicit late-arrival assumptions |
| Data quality and transformation design | 9.1/10 | Typed monetary parsing, standardization, deterministic quarantine identities, and validation paths |
| Gold modeling and analytics | 9.0/10 | One-row-per-order model, payment-grain failure metrics, category impact handling, SCD2 history, and dashboard contracts |
| Automated testing and CI | 8.6/10 | Local Spark tests exercise shared Bronze/Silver/Gold logic; notebook/configuration validation and release packaging run in CI |
| Deployment and operations | 8.5/10 | Sanitized job template, workspace-specific renderer, deployment guide, runbook, and release archive |
| Runtime observability and retained evidence | 7.3/10 | Successful run is owner-confirmed, but run IDs, task logs, reconciliation outputs, populated notebook outputs, dashboard screenshot, and alert-delivery evidence are not retained |

## Senior-level engineering strengths

### 1. Incremental processing is treated as a correctness problem

The Bronze workflow uses a timestamp-plus-primary-key cursor, normalizes timestamp precision, rejects invalid cursor rows, and writes source versions using a replay-aware Delta merge strategy. Silver tracks processed Bronze state independently by entity. Gold tracks unprocessed Silver runs independently for orders, products, and payments.

This gives the implementation a reasoned processing contract rather than relying only on notebook execution order. The important interview discussion is the boundary of that contract: late/backdated changes and hard deletes still require an explicit source-change or reconciliation strategy.

### 2. Data quality is part of the data model

The shared transformation module standardizes order, product, and payment inputs, handles supported US and decimal-comma monetary formats, separates valid and rejected rows, and gives quarantined source versions deterministic identities. That supports repeatable processing and investigation without silently treating malformed values as valid financial measures.

### 3. Gold modeling respects the business grain

The Gold model keeps the reporting fact at one row per order and aggregates successful payment amounts before joining payment data to orders. Payment failure rate is calculated from individual payment attempts rather than the order-level result. The implementation also handles product category changes by refreshing the old and new category aggregates, with SCD2 history helping recover prior category context across a partial-run retry.

These are valuable examples of avoiding fan-out errors and stale aggregates—topics that commonly distinguish a thoughtful data engineer from someone who only knows the syntax of Spark and SQL.

### 4. The repository is designed to be redeployed and reviewed

The saved job JSON is a sanitized template, not a falsely presented live job export. The renderer validates the required task set and dependencies and injects target-workspace paths and resource IDs. The runbook, engineering decisions, data dictionary, artifact audit, validation plan, and clean release package make the project easier for another engineer to inspect.

### 5. Tests exercise transformation behavior, not just file existence

The CI workflow installs Java and PySpark, runs local Spark unit tests, validates notebook Python syntax and imports, checks dashboard and job contracts, parses architecture SVGs, and builds and inspects a clean release ZIP. These tests provide meaningful repository-side confidence, while remaining distinct from a live Databricks integration test.

## Remaining gaps, ranked by value

| Priority | Gap | What is needed |
|---|---|---|
| High | Runtime evidence package | Retain the actual deployed commit, Databricks job/task run IDs, timezone-aware timestamps, concise task logs, row counts, and source-to-target reconciliation from a genuine run |
| High | Incremental edge-case proof | Record controlled equal-timestamp, late-arrival, replay-after-partial-failure, and category-move results; document the chosen lookback/CDC/reconciliation policy |
| High | Live platform integration tests | Add a disposable-environment validation path for Azure SQL federation, Unity Catalog permissions, Delta writes/merges, and the actual Databricks job graph |
| Medium | Dashboard and alert evidence | Attach a genuine populated dashboard screenshot, query/refresh result, and approved SQL-alert test outcome |
| Medium | Operational baselines | Measure representative volume, processing duration, compute cost, failure/retry behavior, and define target freshness and recovery objectives |
| Medium | Source-change completeness | Decide how hard deletes and source changes with missing, unchanged, or backdated timestamps are detected |
| Medium | Synthetic-data disclosure | Keep the case-study status explicit; do not imply that synthetic retail data came from a real retailer |

The scenario-level acceptance tests are enumerated in [VALIDATION_PLAN.md](VALIDATION_PLAN.md). A successful overall run should not automatically mark every row in that matrix as passed.

## Recommended portfolio positioning

> Built an Azure Databricks lakehouse for a retail case study, implementing incremental Bronze ingestion with timestamp/key watermarks, Silver standardization and deterministic quarantine, and Gold order-level and category-level analytics. Added replay-aware Delta merge patterns, per-entity processing controls, SCD Type 2 order history, payment-grain failure metrics, impacted-category refresh logic, dashboard/job configuration, local Spark tests, and CI release packaging. The owner-confirmed end-to-end environment run is documented separately from the repository's repeatable local validation evidence.

For interviews, lead with three design discussions:

1. **Incremental correctness:** why the cursor is composite, how checkpoints advance, what happens after a write succeeds but a checkpoint fails, and why late updates or hard deletes require additional handling.
2. **Model grain:** why payment amounts are aggregated before joining to orders and why failure rate must be calculated at payment-attempt grain.
3. **Recovery and reconciliation:** how a product-category move affects historical/current categories, how SCD2 helps recover state after a partial run, and how incremental Gold should be compared with a full recomputation.

## Release and validation status

At review time, the current `main` head was `2f5d6283aac4006f4628259dc133fc4a6df3bb10`. [GitHub Actions run #130](https://github.com/viradidi/1NOVACART-CASE-STUDY/actions/runs/42073848779) succeeded on that commit. Its job summary reports successful artifact/notebook validation, local Spark tests, clean release archive verification, and artifact upload.

This CI result verifies repository-side checks only. It does not execute Azure SQL, Lakehouse Federation, the Databricks notebooks in a live workspace, dashboard rendering, or SQL alert delivery. The project owner's 5 November 2026 end-to-end run confirmation remains a separate first-party execution statement.

