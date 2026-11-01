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
## Test design and measurement rules

### Build controlled fixtures

Use deterministic fixtures with stable business keys and hand-calculated expected results. Include:
- One order with a single payment, one with multiple payments across successful, failed, and pending statuses, and one with no payment.
- Two orders referencing the same product.
- A product category move that leaves the old category empty.
- Duplicate business keys, null keys where permitted, null timestamps, and equal timestamps with different primary keys.
- A payload update that retains the same key and timestamp, if the source permits it.
- Invalid, null, negative (where permitted), and high-precision monetary values.
- A tracked SCD2 change, exact replay, and out-of-order effective-time change.

Record expected Bronze, Silver, Gold, and history outcomes before execution. Never use production customer data for these fixtures.

### Quantitative acceptance criteria

| Check | Acceptance criterion |
|---|---|
| Business-key uniqueness | Zero unintended duplicate keys in current-state Silver and order-grain Gold |
| Required keys | Zero null values for required business keys |
| Order grain | Exactly one Gold order row per eligible order key |
| Payment aggregation | Paid amount equals the hand-calculated sum for documented successful statuses |
| Payment failure rate | Numerator and denominator use an explicit payment-status set; zero-denominator behavior is defined |
| Category movement | Old and new category totals match independent recomputation; empty-category behavior is explicit |
| SCD2 current rows | Exactly one current version per business key after a tracked change; exact replay creates no unintended version |
| Incremental reconciliation | Incremental Gold and full recomputation match, or each exception is explained and approved |
| Checkpoint integrity | Checkpoint never moves beyond the highest source position whose required target processing succeeded |
| Snapshot integrity | Schema and row count match intended Gold output and publication is associated with the correct successful run |

Do not choose arbitrary percentage tolerances for financial metrics. Define decimal precision, rounding mode, currency handling, and acceptable rounding differences before testing.

## Additional edge-case and failure-injection tests

These scenarios are planned tests, not evidence of execution until results are recorded.

| ID | Scenario | Procedure | Expected result | Evidence to retain |
|---|---|---|---|---|
| VAL-19 | Null source cursor | Introduce a null source timestamp | Explicit reject, fallback, or exception; never silently lost | Source row, query result, quality outcome |
| VAL-20 | Same key/timestamp, changed payload | Change payload without changing primary key or timestamp | Establish whether current MERGE updates or ignores the payload; document contract and mitigation | Before/after payload, merge result, target row |
| VAL-21 | Hard delete | Delete a source row where supported | Detect only if implemented change capture supports it; otherwise record limitation and reconciliation requirement | Source and target state |
| VAL-22 | No-change Silver run | Run Silver with no new Bronze rows | Control metadata and Gold selection remain consistent; no false acknowledgement or duplicate output | Control rows and output counts |
| VAL-23 | Silver write/control boundary | Fail after Silver write but before processing-control acknowledgement | Retry behavior is understood; no un reconciled missing or duplicate output | Failure point, target/control state, retry |
| VAL-24 | Gold write/control boundary | Fail after Gold write but before Gold control acknowledgement | Rerun neither skips affected entities nor creates unintended duplicates | Gold rows, control state, reconciliation |
| VAL-25 | SCD2 out-of-order change | Process a change with effective time earlier than current version | Explicit late-arriving-dimension policy is followed; otherwise case is flagged/rejected | Version timeline and policy outcome |
| VAL-26 | Zero payment denominator | Use fixture with no payments in the denominator status set | Explicit null/zero/not-applicable policy; no divide-by-zero | Input statuses and calculated metric |
| VAL-27 | Financial precision | Include fractional amounts near rounding boundaries | Conversion and aggregation follow documented DECIMAL precision and rounding | Inputs, typed values, expected/actual sums |
| VAL-28 | Empty impacted category | Move the last associated product/order out of a category | Old category removed or retained as zero per contract; no stale total | Impact set and category output |
| VAL-29 | Independent entity progress | Fail one entity while another succeeds, where orchestration permits | Successful entity does not incorrectly acknowledge the failed entity | Per-entity control rows and task results |
| VAL-30 | Snapshot publication failure | Fail publication after Gold succeeds | Previous valid snapshot remains identifiable; incomplete output is not labelled latest successful | Paths, timestamps, run IDs |

## Assertion examples

Translate these examples to the actual deployed catalog, schema, and column names. They express validation intent and are not executable against an unspecified environment.

**One current row per business key**

~~~sql
SELECT business_key, COUNT(*) AS current_rows
FROM silver_dimension
WHERE is_current = TRUE
GROUP BY business_key
HAVING COUNT(*) <> 1;
~~~

Expected result: zero rows for keys expected to have a current dimension record.

**One order-grain row per order**

~~~sql
SELECT order_id, COUNT(*) AS rows_per_order
FROM gold_orders
GROUP BY order_id
HAVING COUNT(*) <> 1;
~~~

Expected result: zero rows.

**No unintended duplicate current-state keys**

~~~sql
SELECT business_key, COUNT(*) AS row_count
FROM silver_current_entity
GROUP BY business_key
HAVING COUNT(*) > 1;
~~~

Expected result: zero rows, after applying the documented current-state filter if the table intentionally stores history.

**Incremental-versus-full reconciliation**

Compare both directions using complete business keys and all contractually defined measures. A FULL OUTER JOIN with null-safe comparisons is preferable to comparing total row counts alone; record missing keys and per-measure differences separately.

## Evidence quality and sign-off

A reviewable validation result includes:
1. Exact repository commit and deployed configuration version.
2. Fixture definition or safe reference to it.
3. Test procedure and failure-injection point, where applicable.
4. Expected and actual results, including key-level or metric-level comparisons.
5. Job/task run identifiers and timestamps with timezone.
6. Query result, log excerpt, or screenshot that exposes no secrets or unnecessary personal data.
7. Final status, reviewer, unresolved limitations, and follow-up issue.

Keep code-review conclusions separate from runtime outcomes. Static inspection can identify risks or show that a test is defined; it cannot establish that a scenario passed in a live Databricks environment. Because the original workspace was decommissioned, these additional scenarios remain planned until executed after redeployment.
