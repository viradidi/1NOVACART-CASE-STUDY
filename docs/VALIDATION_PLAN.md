# NovaCart Validation Plan

## Purpose

This plan defines repeatable acceptance checks for the NovaCart incremental lakehouse pipeline. It distinguishes expected behavior from evidence actually collected. The original Databricks workspace has been decommissioned to control costs; live tests must be executed after redeployment.

## Test prerequisites

- [ ] Redeploy the required Azure SQL and Databricks resources.
- [ ] Restore Lakehouse Federation connection, permissions, catalog, schemas, and required compute.
- [ ] Review workspace-specific notebook paths, dashboard/alert/warehouse IDs, and notification recipients in exported configuration.
- [ ] Use a small, controlled test dataset with known expected outputs.
- [ ] Record repository commit, environment, job/run IDs, timestamps, expected results, actual results, and evidence links.
- [ ] Never store credentials or sensitive source records in GitHub evidence.

## Acceptance matrix

| ID | Scenario | Procedure | Expected result | Evidence to retain |
|---|---|---|---|---|
| VAL-01 | Initial load | Run the pipeline on a known source fixture | Expected source entities appear in Bronze, Silver, and Gold with documented transformations | Source/target counts, key samples, run IDs |
| VAL-02 | No-change rerun | Rerun without changing source data | No unintended duplicate current-state records or unexpected metric changes; control state behaves as designed | Before/after counts, key uniqueness, control rows |
| VAL-03 | New source row | Insert one product, order, and payment test row as applicable | Each new record is detected and reaches the appropriate downstream outputs | Source keys, ingestion metadata, output rows |
| VAL-04 | Existing-row update | Change tracked fields and source change timestamp | Updated values reach Silver and dependent Gold outputs | Before/after values, affected order/category checks |
| VAL-05 | Equal timestamps | Create multiple changes with the same source timestamp | Cursor semantics do not silently skip tied records | Selected keys and saved cursor before/after |
| VAL-06 | Late-arriving update | Change a record whose timestamp falls behind the stored watermark, if the source permits the case | Documented lookback or reconciliation strategy detects it; otherwise the limitation is explicitly recorded | Test record, watermark, detection result |
| VAL-07 | Replay after partial failure | Interrupt a run after the Bronze Delta MERGE commits but before checkpoint update; retry the same source interval | The same primary-key/source-timestamp version is not inserted twice and the checkpoint advances only after successful processing | Failure point, control state, retry run, key/version duplicate check, reconciliation |
| VAL-08 | Silver key uniqueness | Feed duplicate source keys into the batch | Deterministic deduplication or documented rejection occurs before merge | Input duplicates, selected winner/rejected rows, target uniqueness |
| VAL-09 | Invalid amount | Provide malformed or null financial values in a test fixture | Conversion and data-quality behavior matches the documented policy | Rejected/accepted rows and resulting typed values |
| VAL-10 | Payment multiplicity | Use an order with multiple successful, failed, and pending payment records | Exactly one Gold row exists per order; paid_amount sums only the documented successful statuses; payment failure rate is calculated per payment record | Hand-calculated order total, payment-level failure count, output comparison |
| VAL-11 | SCD Type 2 change | Update a tracked business attribute | Prior version closes and a new current version appears according to the model's effective-time rules | History rows before/after and current-row count |
| VAL-12 | SCD Type 2 replay | Replay the same change | No unintended duplicate history version is created | Version history and duplicate checks |
| VAL-13 | Product change impact | Change a product used by existing orders | All affected orders and relevant category metrics are refreshed according to the chosen current-vs-historical product semantics | Impacted keys and category results |
| VAL-14 | Category move | Change a product's category for orders already present in Gold | Both old and new categories are recomputed; an old category with no remaining orders is removed | Full recomputation comparison for old/new categories and category-table contents |
| VAL-15 | Gold reconciliation | Compare incremental Gold outputs with a full recomputation on the same fixture | Order-level and category-level results match under the documented business definitions | Comparison results and explained exceptions |
| VAL-16 | Snapshot publication | Complete a successful Gold run | Latest snapshot corresponds to that run; timestamped snapshot has expected schema and row count | Volume paths, run association, schema/count |
| VAL-17 | Upstream task failure | Cause a controlled upstream failure | Dependent tasks do not execute as though prerequisites succeeded | Job graph and task statuses |
| VAL-18 | Dashboard/alert | Refresh dashboard and test an alert using an approved test condition | Dashboard reflects the validated Gold data and alert behavior matches its condition | Screenshot, query result, test notification record |

## Core data-quality assertions

Adapt names and policies to the actual notebook implementation before execution.

- Business keys are not null where required.
- Current-state tables have no unintended duplicate business keys.
- Gold has exactly one row per order even when payments are one-to-many.
- Source timestamp and primary-key cursor boundaries are deterministic.
- Bronze replay after a committed write does not duplicate the same primary-key/source-timestamp version.
- Gold processes unacknowledged Silver run IDs independently for orders, products, and payments.
- Watermarks advance only after the relevant data write succeeds.
- Monetary strings are converted to numeric types under explicit invalid-value rules.
- Order-level outputs follow a documented grain.
- SCD Type 2 has at most one current version per business key.
- Category metrics reconcile with a full calculation on the same fixture.
- Snapshot schema and row counts correspond to the intended successful Gold run.

## Execution log template

Copy this block for each validation run:

- **Test ID:**
- **Date/time and timezone:**
- **Repository commit:**
- **Environment/configuration:**
- **Job and run IDs:**
- **Test input / fixture:**
- **Expected result:**
- **Actual result:**
- **Pass / fail / blocked:**
- **Evidence link:**
- **Issue or limitation:**
- **Follow-up action:**

## Status policy

Use only these statuses:

- **Not run** — no execution evidence exists yet.
- **Blocked** — execution could not proceed; record the dependency.
- **Pass** — expected result was observed and evidence was retained.
- **Fail** — observed result differed from expected.
- **Not applicable** — explain why the scenario does not apply.

Do not mark a test as passed based solely on code inspection or a successful job status.

## Completion criteria

NovaCart's validation is ready for review when:
1. All applicable core tests have recorded results.
2. Failures have issues or documented resolutions.
3. Incremental outputs reconcile against a full recomputation for controlled test data.
4. Watermark, replay, and late-update behavior is demonstrated or its limitations are clearly documented.
5. The README links to the actual evidence and does not claim unexecuted tests passed.
