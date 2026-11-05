# NovaCart Artifact and Evidence Audit

**Review scope:** repository ZIP archive, exported Databricks dashboard JSON, saved job configuration, and the three checked-in notebooks. This is a review of preserved repository artifacts and committed implementation improvements. The project has previously run in its original environment; the Azure Databricks workspace was later decommissioned to control costs.

## Findings at a glance

| Area | Result | What the artifact proves |
|---|---|---|
| Dashboard export | Structurally readable | A dashboard definition with datasets, filters, KPI counters, and charts is preserved |
| Dashboard data sources | Consistent with the documented Gold model | The export points to `adb_datatocrunchproject.gold_schema.orders_information` and `category_performance` |
| Dashboard runtime evidence | Not verified | The JSON does not prove the dashboard was successfully rendered or queried after export |
| Notebook execution evidence | Historical project run; no saved cell outputs in current exports | The checked-in notebooks preserve implementation code; cell outputs are not embedded in these files |
| ZIP archive | Compared against checked-in notebooks | Corrected exports were compared; code-level mitigations for Gold payment grain, category moves, Bronze replay, checkpoints, and snapshot paths are committed. The archive is not a complete release package. |
| Job configuration | Sanitized to a redeployment template | Personal recipient and old workspace-specific resource IDs have been replaced with placeholders |

## 1. Dashboard artifact review

The checked-in file is [NovaCart Sales & Payments Overview.lvdash.json](../NovaCart%20Sales%20%26%20Payments%20Overview.lvdash.json).

The JSON parses successfully and defines two datasets:

- `orders_information` from `adb_datatocrunchproject.gold_schema.orders_information`
- `category_performance` from `adb_datatocrunchproject.gold_schema.category_performance`

The page definition contains date, category, and order-status filters; KPI counters for GMV, order count, average order value, and payment completion; and visualizations for monthly GMV versus paid amount, payment state, GMV by category, top products by GMV, and category performance. The widget dataset references resolve to dataset names declared in the export.

### Important limitations

- This is a **dashboard configuration export**, not a screenshot of a populated dashboard.
- The saved workspace has been decommissioned. We cannot verify current query execution, rendered values, filter interactions, refresh behavior, or alert delivery from this file alone.
- The Gold notebook now aggregates successful/settled payment amounts before joining at order grain, and computes payment failure rate at payment grain. Confirm the successful-status vocabulary against the source after redeployment; static changes are not runtime reconciliation evidence.
- The category-performance dataset uses a generic row-count measure in its dataset definition; validate each category-table column and metric against the actual Gold schema after redeployment.

### Evidence required for a portfolio claim

After redeployment, retain a screenshot of the rendered dashboard with synthetic/approved data, the successful dashboard query or refresh result, and the corresponding Gold reconciliation results. Until then, describe this as an exported dashboard artifact, not live dashboard evidence.

## 2. ZIP archive inspection

The repository-root file [1NOVACART-CASE-STUDY.zip](../1NOVACART-CASE-STUDY.zip) is approximately 66 KB and contains 85 ZIP entries. The archive includes `bronze_work.py`, `silver_work.py`, and `gold_work.py` exports. The user clarified that these are the corrected notebook exports downloaded after earlier pushed code did not work correctly. **Do not label those exports stale solely because they are `.py` files rather than `.ipynb` notebooks.** Their code must be compared with the current GitHub notebooks before deciding which version is authoritative. The archive listing also shows:

- A full `1NOVACART-CASE-STUDY/.git/` directory, including object packs, refs, branch names, logs, and Git metadata.
- Python exports named `bronze_work.py`, `silver_work.py`, and `gold_work.py`.
- A small `README.md` (25 bytes), plus `manifest.mf`.
- No `NovaCart Sales & Payments Overview.lvdash.json` entry.
- No current `*.ipynb` notebooks or the current `docs/` engineering documentation in the archive listing.

The ZIP is **not a self-contained copy of the entire current GitHub project** because it does not include the dashboard JSON or current engineering documentation, and it includes `.git/` metadata that does not need to be distributed. The code comparison is complete. The export contained Bronze timestamp normalization and null-primary-key watermark handling, Silver run-ID metadata, and a Gold payment timestamp correction. Those corrections were applied. Further code-level mitigations now address one-row-per-order Gold grain, payment-level failure rate, old/new category refresh after product moves, replay-safe Bronze MERGE, per-entity Gold processing checkpoints, and standardized snapshot paths. The export also contained an invalid `collect()["mx"]` pattern in the product section; the notebook uses `collect()[0]["mx"]` instead. A clean release archive should exclude `.git/` and include the dashboard and current documentation.

## 3. Notebook evidence and static review

The current repository contains all three notebooks:

- [Bronze](../bronze_work.ipynb): 16 cells, 9 code cells.
- [Silver](../silver_work.ipynb): 26 cells, 17 code cells.
- [Gold](../gold_work.ipynb): 26 cells, 15 code cells.

The checked-in notebooks contain no saved code-cell outputs. They preserve implementation code, but they do not by themselves prove successful execution or expected row counts.

Static review led to the following code-level mitigations. All remain subject to runtime validation after redeployment:

1. **Bronze append/checkpoint boundary — code mitigation applied:** Bronze now MERGEs on the source primary key plus source change timestamp, preserving distinct versions while avoiding duplicate inserts after a failure between the data write and checkpoint update. Null primary keys or watermark timestamps are rejected before writing. This is a static code change; controlled failure/replay validation is still pending.
2. **Source catalog name:** Bronze references `project-datatocruch_catalog`. Confirm that this is the exact foreign-catalog name in the intended environment; do not rename it blindly if it is the actual configured name.
3. **Payment grain in Gold — code mitigation applied:** Gold is explicitly order-grain. It aggregates successful/settled payment amounts by order before joining, retains the latest payment ID/status as descriptive fields, and calculates payment failure rate at payment grain from Silver payments. A uniqueness guard rejects a Gold delta with multiple rows per order. Validate the status mapping against the source's actual payment-status vocabulary after redeployment.
4. **Category changes — code mitigation applied:** Gold captures categories from existing Gold rows for impacted orders before merging, unions those with the new categories, recomputes aggregates for both sides of a move, and removes an obsolete category aggregate if no Gold orders remain in that category. The payment failure metric is recomputed at payment grain. Compare incremental output with a full recomputation after redeployment.
5. **Historical snapshot path names — code mitigation applied:** Gold now writes to `gold_snapshots` and `category_performance`, and sanitizes colons in the run timestamp path component. The former workspace was deleted, so no live migration was performed. If an older environment is restored, migrate legacy folders deliberately.

The code-level mitigations above are committed as improvements to the working implementation. Since the original workspace was decommissioned, these latest changes have not been exercised in that retired environment. Use [the validation plan](VALIDATION_PLAN.md) for focused regression checks when a workspace is next available; do not interpret the absence of a current workspace as meaning the project itself is unfinished.

## 4. Public job configuration

The repository's `novacart_job.json` has been changed into a **redeployment template**: the personal notification recipient and workspace-specific notebook/resource IDs have been removed or replaced with explicit placeholders. Before import, replace notebook paths, dashboard ID, alert ID, and warehouse ID with valid values from the target workspace. This template is not directly runnable until those values are set.

## 5. Automated release packaging

The repository now includes [a GitHub Actions packaging workflow](../.github/workflows/package-novacart-release.yml) and [release-package instructions](RELEASE_PACKAGE.md). On pushes to `main`, or manual dispatch, the workflow:

- Parses the three notebook exports, job JSON, and dashboard JSON as JSON.
- Parses `docs/novacart-architecture.svg`.
- Checks README links targeting `docs/`.
- Builds `NovaCart-Release.zip`, excluding the legacy root ZIP, the output ZIP itself, and files under `.git/`.
- Uploads the archive as a `NovaCart-Release` Actions artifact for 30 days.

This provides an automated clean-package path without requiring a Databricks workspace. It does **not** execute Bronze/Silver/Gold, validate SQL semantics, verify both architecture SVGs, render or query the dashboard, or prove that the packaged pipeline runs in Databricks. The workflow checks only the architecture SVG named above; the end-to-end SVG is included in the archive but is not currently XML-validated by this workflow. The workflow also uploads a temporary Actions artifact rather than committing a release ZIP to the repository.

The legacy `1NOVACART-CASE-STUDY.zip` remains in the repository as a historical export; it is excluded from the generated clean package. To distribute the current project, use the latest successful `Package NovaCart release` workflow artifact, not the legacy ZIP. Confirm an actual successful workflow run before describing a particular release artifact as generated and available.

## Release readiness and next milestone

The main implementation, targeted correctness improvements, and automated clean-package workflow are committed. The legacy root ZIP remains for historical reference, but the workflow excludes it and packages the current repository contents into a downloadable Actions artifact. The remaining release step is operational: confirm a successful packaging run and retrieve its artifact when needed. When a cloud workspace is next available, run focused regression scenarios for payment multiplicity, category moves, replay after partial failure, per-entity checkpoints, and Gold reconciliation. Those are follow-up regression checks for the latest changes, not a reclassification of the project as non-working.


## 6. Follow-up hardening after this audit

The dashboard export has been updated so the `category_performance` dataset declares the category dimension and explicit business measures for total orders, GMV, total paid, average payment completion, and payment failure rate. The category table widget continues to reference the corresponding source columns. A repository-side dashboard contract test checks the declared measures and widget-to-dataset reference.

The sanitized job JSON remains a template by design. A new `deployment/render_novacart_job.py` utility now generates a target-workspace job definition from real dashboard, alert, warehouse, and workspace-path inputs. It validates required tasks, dependencies, and single-run concurrency. Unit tests cover rendering, required IDs, immutable template handling, and absolute workspace paths. The GitHub Actions workflow now runs the repository's unittest suite before packaging.

These changes improve configuration correctness and deployment reproducibility. They do not create cloud resources, verify that supplied IDs exist, render the dashboard, or execute the notebooks.

## 7. Evidence still unavailable or outstanding

- **Notebook cell outputs:** the checked-in notebooks still contain no saved outputs. The original workspace has been decommissioned, so genuine execution outputs, row counts, and run metadata cannot be recovered from the notebooks. Capture them during the next live run; do not synthesize notebook output cells.
- **Dashboard screenshot:** the committed artifact remains a dashboard configuration export. A real screenshot requires importing or recreating the dashboard in a live Databricks workspace and rendering it against approved test data. A generated mockup must not be presented as a real dashboard screenshot.
- **Transformation tests:** local Spark tests now execute the shared Bronze cursor, Silver order/product/payment cleaning and quarantine identity, Gold payment rollup and category metrics. These are unit tests of extracted functions, not a live Delta MERGE / Unity Catalog / Lakehouse Federation integration test.
- **Live validation:** the workspace-specific job renderer has not deployed or run a Databricks job. Notebook execution, dashboard refresh, alert delivery, and the validation-plan scenarios remain blocked until the environment is recreated.

The repository-side transformation coverage is now implemented and wired into GitHub Actions with Java 17 and PySpark 3.5.1. The next milestone is confirming the workflow run is green, then performing full Databricks/Delta integration and evidence capture when the workspace is recreated.


## 8. Additional repository verification and hardening

The shared transformation module now parses monetary strings according to their separators. It handles US-style values such as `$1,234.50`, decimal-comma values such as `100,00`, and European thousands-plus-decimal values such as `1.234,56`; malformed strings become null and are handled by the existing Silver validation/quarantine rules. This closes a material issue in the supplied synthetic SQL data, which intentionally contains comma-decimal values.

Silver quarantine records now receive a deterministic `quarantine_id` derived from the entity business key and source change timestamp. The Silver notebook uses a Delta MERGE on that ID rather than append-only writes, preventing duplicate quarantine records if a task is retried after quarantine persistence but before its processing checkpoint is recorded. Existing quarantine tables created before this schema change must be migrated or recreated; the notebook intentionally stops with a clear error when it encounters an old schema rather than silently falling back to duplicate-prone appends.

The old Silver one-time orders-cleaned backfill and ad-hoc debug query cells have been removed from the scheduled notebook. They were not part of the normal incremental contract and could overwrite the cleaned table with an arbitrarily selected historical duplicate. Gold no longer displays entire changed-order and Gold-delta DataFrames in a scheduled job, avoiding large notebook result payloads.

The strengthened CI checks notebook Python syntax, shared-module imports, both architecture SVGs, test modules, the dashboard/job configuration contracts, local Spark transformation behavior, and the release archive contents. Generated Python caches and the legacy ZIP are excluded from the release package.


## 9. Gold category-move recovery across partial-run retries

The Gold notebook now initializes the SCD2 table before the current-state Gold merge when needed, then derives the impacted category set after the SCD2 update from the current Gold rows, the new Gold delta, and all historical categories for impacted orders in `orders_information_scd2`. This preserves the old category as durable evidence if a retry starts after the current-state merge has already replaced the prior category.

A local Spark regression test covers the recovery condition where current Gold already contains the new category but SCD2 history retains both old and new categories. The test asserts that both categories remain in the retry's impacted set. This tests the extracted selection helper; full notebook failure injection and Delta transaction behavior still need a live Databricks run.


## 10. Payment attempt versus valid payment semantics

Gold now uses two distinct Silver payment feeds deliberately:
- `payments_transformed` supplies validated current payment rows for paid-amount rollups.
- `payments_cleaned` supplies the latest cleaned attempt status and payment-grain failure-rate population, including attempts whose amount is quarantined. Rows with a null payment status are excluded from the failure-rate denominator.

The Gold local Spark tests cover this separation: a failed attempt with a null amount is still the latest payment status, is counted in payment failure rate, and does not contribute to paid amount. This keeps payment-health signals from disappearing merely because an amount field failed validation.


## 11. Last-known-good and SCD2 integrity controls

The Silver notebooks merge only valid records into the `*_transformed` tables. An invalid newer source version is written to the cleaned/quarantine path, while the previous valid transformed row remains as last-known-good state. This is intentional: it prevents bad source values from corrupting current analytics, but it means transformed data can be stale until the invalid source is corrected and reprocessed. The repository documentation now calls out this behavior and the separate hard-delete limitation.

Gold now uses cleaned payment attempts for latest status and failure-rate metrics, while validated transformed payment rows supply paid amount. The notebook also checks for duplicate current SCD2 versions and current Gold orders missing a current SCD2 history row after its SCD2 update. These guards are covered by local Spark helper tests; the full Delta notebook sequence still requires live execution.
