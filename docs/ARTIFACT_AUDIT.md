# NovaCart Artifact and Evidence Audit

**Review scope:** repository ZIP archive, exported Databricks dashboard JSON, saved job configuration, and the three checked-in notebooks. This is a static review of the repository artifacts, not a live Databricks execution.

## Findings at a glance

| Area | Result | What the artifact proves |
|---|---|---|
| Dashboard export | Structurally readable | A dashboard definition with datasets, filters, KPI counters, and charts is preserved |
| Dashboard data sources | Consistent with the documented Gold model | The export points to `adb_datatocrunchproject.gold_schema.orders_information` and `category_performance` |
| Dashboard runtime evidence | Not verified | The JSON does not prove the dashboard was successfully rendered or queried after export |
| Notebook execution evidence | Not present in the checked-in notebooks | Code cells have no saved output results |
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

The code-level mitigations above are committed, but they have not been executed against a live Databricks workspace. They are not runtime-pass claims. Use [the validation plan](VALIDATION_PLAN.md) to record results after redeployment.

## 4. Public job configuration

The repository's `novacart_job.json` has been changed into a **redeployment template**: the personal notification recipient and workspace-specific notebook/resource IDs have been removed or replaced with explicit placeholders. Before import, replace notebook paths, dashboard ID, alert ID, and warehouse ID with valid values from the target workspace. This template is not directly runnable until those values are set.

## Next evidence milestone

1. Complete a targeted review of the remaining Gold grain, category-move, and Bronze append/checkpoint risks listed above; then prepare a clean ZIP that includes the corrected notebooks, dashboard, and docs while excluding `.git/`.
2. Redeploy only when you are ready to incur cloud costs.
3. Run the validation scenarios for payment multiplicity, category moves, replay after partial failure, per-entity checkpoints, and Gold reconciliation.
4. Save actual run/query evidence and a rendered dashboard screenshot before describing those checks as passed.
