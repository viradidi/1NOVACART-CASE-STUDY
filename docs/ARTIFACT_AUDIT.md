# NovaCart Artifact and Evidence Audit

**Review scope:** repository ZIP archive, exported Databricks dashboard JSON, saved job configuration, and the three checked-in notebooks. This is a static review of the repository artifacts, not a live Databricks execution.

## Findings at a glance

| Area | Result | What the artifact proves |
|---|---|---|
| Dashboard export | Structurally readable | A dashboard definition with datasets, filters, KPI counters, and charts is preserved |
| Dashboard data sources | Consistent with the documented Gold model | The export points to `adb_datatocrunchproject.gold_schema.orders_information` and `category_performance` |
| Dashboard runtime evidence | Not verified | The JSON does not prove the dashboard was successfully rendered or queried after export |
| Notebook execution evidence | Not present in the checked-in notebooks | Code cells have no saved output results |
| ZIP archive | Stale / unsuitable as the current project package | It includes a `.git/` directory and old Python exports, but not the current dashboard JSON or current repository documentation |
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
- KPI calculations depend on the correctness and grain of the Gold tables. In particular, order-level GMV and paid amount can be wrong if the Gold pipeline arbitrarily reduces multiple payment rows to one row per order. Validate the model before treating the displayed values as reconciled business metrics.
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

The ZIP is **not a self-contained copy of the entire current GitHub project** because it does not include the dashboard JSON or current engineering documentation, and it includes `.git/` metadata that does not need to be distributed. However, it may contain the corrected implementation code. Do not replace or discard its notebook exports until their code is compared against the GitHub notebooks. A clean release archive should preserve the corrected notebook code while excluding `.git/` and including the dashboard and current documentation.

## 3. Notebook evidence and static review

The current repository contains all three notebooks:

- [Bronze](../bronze_work.ipynb): 16 cells, 9 code cells.
- [Silver](../silver_work.ipynb): 26 cells, 17 code cells.
- [Gold](../gold_work.ipynb): 26 cells, 15 code cells.

The checked-in notebooks contain no saved code-cell outputs. They preserve implementation code, but they do not by themselves prove successful execution or expected row counts.

Static review identified these correctness risks to address before claiming production-grade incremental correctness:

1. **Bronze append/checkpoint boundary:** Bronze appends raw rows and then updates its watermark. A failure after the append but before the checkpoint update can replay the same source rows. Verify downstream deduplication or add a replay-safe write strategy and test a controlled failure.
2. **Source catalog name:** Bronze references `project-datatocruch_catalog`. Confirm that this is the exact foreign-catalog name in the intended environment; do not rename it blindly if it is the actual configured name.
3. **Payment grain in Gold:** Gold joins orders to payments and then calls `dropDuplicates(["order_id"])`. If an order can have multiple payment records, an arbitrary payment row can be retained, causing paid amount/status metrics to be incomplete. Define the intended payment aggregation or order/payment grain before joining.
4. **Category changes:** The incremental category aggregation derives impacted categories from the new Gold delta. If a product moves from one category to another, the old category may not be recalculated. Test both old and new categories against a full recomputation.
5. **Historical snapshot path names:** The current Gold notebook writes under `gold_snpshots` and `category_peroformance`. These misspellings are consistent in the current code, but they should be corrected deliberately before standardizing downstream paths; if historical data already exists in a live environment, plan a migration rather than silently changing paths.

These are code-review findings and test targets, not claims that a production incident occurred. Use [the validation plan](VALIDATION_PLAN.md) to record results.

## 4. Public job configuration

The repository's `novacart_job.json` has been changed into a **redeployment template**: the personal notification recipient and workspace-specific notebook/resource IDs have been removed or replaced with explicit placeholders. Before import, replace notebook paths, dashboard ID, alert ID, and warehouse ID with valid values from the target workspace. This template is not directly runnable until those values are set.

## Next evidence milestone

1. Compare the ZIP's corrected `.py` notebook exports with the GitHub `.ipynb` notebooks; retain the corrected implementation, then prepare a clean ZIP that also includes the dashboard and docs and excludes `.git/`.
2. Redeploy only when you are ready to incur cloud costs.
3. Run the validation scenarios for payment multiplicity, category moves, replay after partial failure, and Gold reconciliation.
4. Save actual run/query evidence and a rendered dashboard screenshot before describing those checks as passed.
