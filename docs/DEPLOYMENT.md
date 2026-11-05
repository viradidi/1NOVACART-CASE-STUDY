# NovaCart Deployment Guide

This guide explains how to recreate the NovaCart case-study environment from the artifacts in this repository.

> **Project status: WORKING IMPLEMENTATION.** NovaCart was implemented and run in its original Azure Databricks environment. That workspace was later deleted to control costs, so the project is not currently hosted. This guide covers restoring the cloud environment if a live demonstration or regression run is needed. Cloud resource names, IDs, permissions, networking, and credentials must be configured for the target environment.

## 0. Render the workspace-specific job definition

The committed `novacart_job.json` is intentionally a sanitized template. Do not replace its placeholders with invented IDs or commit a workspace-specific export containing personal resource identifiers.

After creating the target notebooks, dashboard, SQL alert, and SQL warehouse, render a job definition using the real identifiers from that workspace:

```bash
python deployment/render_novacart_job.py \
  --template novacart_job.json \
  --workspace-root /Workspace/Shared/NovaCart \
  --dashboard-id "<DASHBOARD_ID>" \
  --alert-id "<ALERT_ID>" \
  --warehouse-id "<WAREHOUSE_ID>" \
  --output novacart_job.rendered.json
```

The renderer rewrites the three notebook paths under the selected workspace root, injects the dashboard/alert/warehouse IDs, checks required tasks and dependencies, and preserves single-run concurrency. The generated file is environment-specific; keep it out of source control unless the target IDs are deliberately non-sensitive and intended to be public. The renderer does not create Databricks resources or prove that the IDs exist.

## 1. Deployment overview

The intended flow is:

1. Provision Azure SQL Database and load the source tables.
2. Provision Azure Databricks and configure Unity Catalog.
3. Configure Lakehouse Federation access to Azure SQL.
4. Import notebooks and configure catalog, schema, and storage resources.
5. Run Bronze, Silver, and Gold sequentially.
6. Recreate the dashboard and alert.
7. Recreate the Databricks Job and validate repeat runs.

Do not begin by scheduling the job. First validate the source connection, initial load, incremental changes, and business outputs interactively.

## 2. Repository artifacts

| Artifact | Purpose |
|---|---|
| `sql-tables-creation.sql` | Source table definitions |
| `initial-load-for-mess-data.sql` | Initial source-data load script |
| `IncrementalLoad-1.sql`, `IncrementalLoad-2.sql` | Example incremental source-load scripts |
| `bronze_work.ipynb` | Bronze ingestion workflow |
| `silver_work.ipynb` | Silver cleansing and transformation workflow |
| `gold_work.ipynb` | Gold business-modeling workflow |
| `novacart_transformations.py` | Shared, unit-tested Spark transformations imported by all three notebooks |
| `NovaCart Sales & Payments Overview.lvdash.json` | Exported dashboard definition |
| `novacart_job.json` | Saved orchestration configuration |
| `docs/novacart-architecture.svg` | Architecture diagram |

Review notebook parameters and SQL scripts before running them. Do not assume every workspace-specific setting will work unchanged in a new environment.

## 3. Prerequisites

Prepare the following in the target Azure environment:

- An Azure subscription with permission to create the required resources.
- Azure SQL Database with the required source tables and sample data.
- Azure Databricks workspace with compatible compute and Unity Catalog enabled.
- Network connectivity and permissions for Databricks to access Azure SQL.
- A supported Lakehouse Federation connection to the SQL source.
- A catalog, schemas, and storage/Volume resources matching the notebooks or updated consistently.
- Appropriate permissions to create Delta tables, jobs, dashboards, and SQL alerts.

Exact compute sizes, cloud resource names, region, runtime, and networking options depend on the target environment and should be selected deliberately rather than inferred from the export files.

## 4. Create and load the source database

> **Destructive setup warning:** `sql-tables-creation.sql` drops the existing `dbo.payments`, `dbo.orders`, and `dbo.products` tables before recreating them. `initial-load-for-mess-data.sql` deletes all rows from those three tables before loading its synthetic fixture. Use these scripts only against a disposable development database that contains no data you need to retain. Do not run them against production or an existing shared database.

1. Create the Azure SQL database.
2. Open and review `sql-tables-creation.sql`.
3. Run the script in the intended database to create the `products`, `orders`, and `payments` tables.
4. Review the initial-load script and run it only after confirming the target tables are empty or that its behavior is safe for the current data.
5. Validate primary keys, foreign-key relationships, timestamp columns, and representative row counts.

The source model uses product and order update timestamps and a payment processing timestamp. Confirm that the source schema matches the assumptions in the notebooks, including data types for amount fields and timestamp handling.

## 5. Configure Databricks and Lakehouse Federation

1. Create or select the target Azure Databricks workspace.
2. Configure Unity Catalog and the permissions required for the deployment.
3. Create the SQL connection and foreign catalog using the current Databricks-supported Lakehouse Federation setup for Azure SQL.
4. Configure authentication through an approved identity or secret-management method.
5. Validate that the Databricks principal can read the three source tables.
6. Update the notebooks to use the actual foreign catalog and source schema names.

Do not place passwords, access tokens, or connection secrets in notebooks or GitHub. Use your organization's approved secret-management and identity configuration.

## 6. Configure catalogs, schemas, and storage

The saved notebook code references the catalog name `adb_datatocrunchproject` and schemas including `bronze_schema` and `gold_schema`. Treat these as development-environment values, not universal defaults.

Before execution:

- Decide the target catalog and schema names.
- Search notebook code for hard-coded catalog, schema, Volume, and table names.
- Create the required schemas and Volume using supported Databricks interfaces or SQL.
- Update all references consistently.
- Confirm that the execution identity has the required read, write, and create permissions.
- Inspect the control-table definitions and confirm the expected columns before processing.

Do not blindly run DDL copied from an old workspace without reviewing it for ownership, permissions, and resource names.

## 6A. Existing quarantine-table migration

The current Silver notebook writes quarantine rows with a deterministic `quarantine_id`. A newly created quarantine table receives this column automatically on its first write. If a target workspace already contains quarantine tables from an older version, migrate them before running the updated Silver notebook.

For each existing table, add the nullable column and populate it from the source business key and source change timestamp. Example for orders:

```sql
ALTER TABLE adb_datatocrunchproject.silver_schema.orders_quarantine
ADD COLUMNS (quarantine_id STRING);

UPDATE adb_datatocrunchproject.silver_schema.orders_quarantine
SET quarantine_id = sha2(
  concat_ws('||', CAST(order_id AS STRING), CAST(updated_at AS STRING)),
  256
)
WHERE quarantine_id IS NULL;
```

Apply the same pattern to `products_quarantine` using `product_id` and `updated_at`, and to `payments_quarantine` using `payment_id` and `processed_at`. Before running the updated notebook, verify that every existing quarantine row has a non-null ID and inspect any duplicate IDs. Resolve duplicates according to the retained source-version policy. The notebook refuses to write to an old quarantine schema that lacks this ID rather than reverting to append-only behavior.

## 7. Import and run the notebooks

Import the three notebook files and `novacart_transformations.py` into the same target workspace folder. The notebooks resolve the helper module relative to their own workspace folder, so keep the four files together. Update source references and configuration first.

Run them in this order:

### Bronze

- Confirm source access and timestamp/key columns.
- Inspect the ingestion control table and initial watermark behavior.
- Run the initial load.
- Compare source and Bronze counts using a clearly defined reconciliation rule.
- Run again without source changes and confirm that no unintended duplicate ingestion occurs.

### Silver

- Confirm the expected Bronze tables and control metadata exist.
- Run cleansing, standardization, deduplication, data-quality handling, and merge logic.
- Inspect rejected or quarantined records if the implementation creates them.
- Re-run with no new source changes and verify expected idempotent behavior.
- Test a source update and confirm that the Silver record changes correctly.

### Gold

- Confirm the expected Silver tables and processing-control state.
- Run the Gold workflow.
- Inspect `orders_information`, `orders_information_scd2`, and `category_performance`.
- Confirm that current-state order values, historical versions, and category metrics agree with the source and defined business rules.
- Confirm that expected Volume snapshots are written.
- Run again without changes and check that the results remain consistent.

These are deployment acceptance checks for a newly recreated environment. They complement the existing working implementation and are intended to confirm environment-specific behavior after redeployment.

## 8. Restore dashboard and alert

The repository includes an exported dashboard definition. Import support and steps may vary with the current Databricks dashboard experience, so use the current workspace UI or supported API for the target environment.

1. Import or recreate the dashboard.
2. Review each dataset/query reference and update catalog, schema, and warehouse settings.
3. Validate the dashboard against the Gold tables.
4. Recreate the SQL alert and define the intended condition, evaluation schedule, and recipients.
5. Verify alert behavior with a controlled test condition before enabling operational notifications.

The exported files may contain workspace-specific identifiers. An export is a configuration artifact, not proof that the dashboard, warehouse, or alert still exists.

## 9. Recreate orchestration

The `novacart_job.json` file documents the intended dependency order:

`bronze_work → silver_work → gold_work → novacart_dashboard → n_alert`

The saved configuration uses `ALL_SUCCESS` dependencies, enables queuing, and sets `max_concurrent_runs` to `1`.

Before importing or recreating the job:

- Replace the old workspace notebook paths with the new paths.
- Replace old dashboard, alert, and warehouse IDs with IDs from the new workspace.
- Remove or replace personal email subscriptions and configure the intended recipients.
- Confirm task names, task types, permissions, and dependency references.
- Choose an appropriate schedule only after manual runs pass the acceptance checks.
- Configure timeouts and failure notifications according to the operational requirements.

Use the saved JSON as a reference and review it before submitting it to the target workspace. Do not expect old resource IDs to resolve in a new workspace.

## 10. Acceptance checklist

Before considering the redeployment complete, record evidence for each item.

- [ ] Databricks can read all required Azure SQL source tables.
- [ ] Bronze initial load completes and its watermark/control metadata is correct.
- [ ] A no-change rerun does not create unintended duplicates.
- [ ] A source insert is processed through the expected layers.
- [ ] A source update is reflected in the appropriate current-state table.
- [ ] Silver data-quality and deduplication rules behave as intended.
- [ ] Gold order and category metrics reconcile with agreed business definitions.
- [ ] SCD Type 2 history changes only when tracked attributes change.
- [ ] Volume snapshots are created at the expected paths.
- [ ] Dashboard queries return the intended results.
- [ ] The alert condition has been tested.
- [ ] The job completes in dependency order and failures are visible.
- [ ] A failed run can be investigated and safely rerun.
- [ ] Compute shutdown/auto-termination and budget controls are configured.

Capture concise evidence such as run output, row-count comparisons, test results, and screenshots. Do not publish credentials, personal information, or sensitive source data.

## 11. Cost and cleanup

For a portfolio deployment, keep the environment short-lived and cost-aware:

- Start compute only when needed.
- Configure auto-termination and avoid unnecessarily large clusters.
- Avoid running schedules while not actively demonstrating the project.
- Check Azure Cost Management for related resources, not only the Databricks workspace.
- Preserve required notebooks, exports, documentation, and non-sensitive test data before deleting resources.
- After the demonstration, stop or remove resources that are no longer required.

Deleting a workspace may not automatically remove every separately provisioned Azure resource. Review the resource group and billing view before assuming all charges have stopped.

## 12. Deployment evidence

When a future deployment is available, add a short record here or in a separate evidence document containing:

- Deployment date and non-sensitive environment overview.
- Runtime and relevant configuration versions.
- Initial-load and incremental-run results.
- Reconciliation and data-quality results.
- Job outcome and failure/recovery evidence.
- Dashboard screenshots using synthetic or approved data.

Until that evidence exists, describe the project as a documented, redeployable case study with saved implementation artifacts—not as a currently running cloud service.

## 13. Environment configuration and portability

Maintain a small deployment configuration record for each environment. Avoid editing notebook logic independently in multiple places.

| Setting | Example value | Deployment rule |
|---|---|---|
| Workspace | Target Databricks workspace | Record workspace URL/name; never assume old workspace IDs remain valid |
| Source foreign catalog | Environment-specific catalog | Verify the exact catalog and schema against the live connection |
| Processing catalog | Environment-specific catalog | Use one reviewed value consistently across notebooks and SQL |
| Bronze/Silver/Gold schemas | Layer-specific schema names | Create explicitly and verify grants |
| Source connection | Approved federation connection | Use managed identity/approved credentials; never commit secrets |
| Snapshot Volume | Target catalog/schema/Volume | Create and test permissions before Gold publication |
| Job/task paths | Target workspace notebook paths | Replace exported paths and validate every task reference |
| Dashboard/alert/warehouse | New workspace resource IDs | Recreate and record new IDs; do not reuse stale export IDs |
| Notifications | Approved operational recipients | Remove personal or obsolete subscriptions |

Before the first run, perform a repository-wide configuration review for hard-coded catalog names, schema names, Volume paths, workspace paths, and resource IDs. The notebooks and exported job definition are implementation artifacts from the original environment, not a parameterized deployment package. Record each required change and validate it in the target workspace.

### Catalog and source-name verification

The notebook artifacts contain environment-specific catalog identifiers. In particular, verify the Bronze source catalog reference against the actual Lakehouse Federation foreign catalog and verify that the processing catalog is the intended Unity Catalog catalog. Do not assume similarly named catalog strings are interchangeable. Confirm the source tables are visible to the job's execution identity before running any write task.

## 14. Safe source database provisioning

The source DDL includes destructive reset behavior. Treat it as a test-fixture reset script, not a repeatable production deployment migration.

Recommended sequence:

1. Review the SQL script and identify every DROP, TRUNCATE, DELETE, and CREATE statement.
2. Confirm the target database and environment before executing any destructive statement.
3. Use a disposable database for the portfolio fixture.
4. Separate schema provisioning from test-data reset so that a routine deployment does not erase existing data.
5. Prefer versioned, reviewed migrations and non-destructive create/alter operations for persistent environments.
6. Load synthetic fixture data and validate primary/foreign-key relationships, timestamp columns, and monetary types.
7. Capture the source schema version and fixture identifier used for the run.

Do not run the reset script against a database containing data that must be retained. If the source schema is changed, update the data dictionary, source contract, notebooks, and validation fixtures together.

## 15. Deployment sequence with gates

Use these gates to avoid scheduling a workflow before its dependencies and semantics have been verified.

| Gate | Required checks | Proceed only when |
|---|---|---|
| D0 — Cost and scope | Resource group, region, budget, auto-termination, cleanup plan | Cost owner and disposable scope are clear |
| D1 — Source | Tables, keys, timestamps, types, fixture data, source permissions | Source contract and expected rows are verified |
| D2 — Federation | Connection, authentication, network path, catalog visibility | Job identity can read all required source objects |
| D3 — Unity Catalog | Processing catalog, layer schemas, Volume, grants | Required read/write/create permissions are tested |
| D4 — Notebook portability | Paths, catalog references, schema names, parameters | No stale workspace-specific references remain |
| D5 — Layer execution | Bronze, then Silver, then Gold; inspect each output | Each layer's acceptance checks pass before the next |
| D6 — Consumer artifacts | Snapshot, dashboard queries, alert condition | Consumer outputs match validated Gold data |
| D7 — Orchestration | Job paths, task types, dependencies, concurrency, queueing, notifications | Manual end-to-end run and recovery tests pass |
| D8 — Schedule | Schedule, timeout, notifications, budget alerts | Owner explicitly approves ongoing execution |

If a gate fails, stop at that gate. Do not compensate by manually advancing checkpoints or suppressing downstream task failures.

## 16. First-run and incremental-run procedure

For the first deployment, preserve a clear boundary between initial population and incremental processing:

1. Record the source fixture identifier and baseline row counts.
2. Confirm the initial watermark behavior for each entity. Establish how null/uninitialized watermarks are represented and handled.
3. Run Bronze and validate selected source keys against landed keys.
4. Run Silver and validate required keys, deduplication, accepted/rejected records, and typed values.
5. Run Gold and validate order grain, payment measures, category metrics, and SCD2 current/history rows.
6. Record the final control state for each entity and layer.
7. Add one controlled insert and one update with a source timestamp greater than the saved cursor; rerun the layers in dependency order.
8. Validate timestamp ties, same-key/same-timestamp payload changes, and late-arriving changes according to the source contract.
9. Compare incremental Gold with an independent full recomputation on the same fixture.
10. Only after these checks pass, configure the scheduled job.

A successful task status is not sufficient by itself. Retain key-level and metric-level reconciliation results.

## 17. Redeployment-specific implementation checks

Resolve these known questions before treating a redeployed environment as production-like:

- **Bronze MERGE semantics:** Inspect the actual merge condition and matched clauses. If matching uses both primary key and source timestamp and the implementation only inserts unmatched rows, a changed payload with an unchanged key/timestamp may not update the target. Test this explicitly.
- **Silver no-change behavior:** Confirm how Silver records processing success when no Bronze rows are emitted, and how Gold consumes that control record. Ensure the resulting run identifier cannot cause a false acknowledgement or skip.
- **Timestamp completeness:** Confirm every relevant source mutation advances the timestamp. If not, choose CDC, a source change log, or a bounded reconciliation strategy.
- **Deletes:** Timestamp filtering does not inherently capture hard deletes. Define tombstone/CDC or periodic reconciliation behavior if deletes matter.
- **Monetary types:** If source amounts are stored as strings, define conversion to an appropriate DECIMAL precision and the handling of invalid, null, negative, and over-precision values.
- **SCD2 temporal policy:** Define behavior for late-arriving changes, out-of-order effective timestamps, and replayed changes before relying on historical outputs.
- **Job concurrency:** A job-level maximum of one concurrent run prevents overlapping runs of that job, but does not protect against other jobs or external writers modifying the same targets.

Record each decision in the engineering decisions and validation documents, and retain test evidence for any claim of verified behavior.

## 18. Rollback, cleanup, and cost guardrails

Before deployment, define what can be safely rolled back and what must be preserved:

- Preserve the current control-table state and affected target data before any destructive rebuild or manual correction.
- Keep the previous known-good notebook/configuration version and record the repository commit deployed.
- For a failed release, pause the schedule first; determine whether writes committed before deciding to rerun, restore, or rebuild.
- Do not roll a checkpoint backward or forward without a bounded replay plan and reconciliation.
- Confirm snapshot consumers and retention requirements before deleting prior outputs.
- Configure compute auto-termination, job schedules, SQL warehouse start/stop behavior, and budget notifications.
- After a demonstration, stop compute and remove only the resources explicitly included in the cleanup plan.
- Verify the Azure resource group and billing view after cleanup; deleting a Databricks workspace alone may not remove all separately provisioned resources.

## 19. Deployment record template

Use this record for each redeployment. Do not include credentials, secret values, or sensitive customer data.

- **Deployment date/time and timezone:**
- **Repository commit:**
- **Azure region / resource group:**
- **Databricks runtime and compute:**
- **Source database/schema version:**
- **Foreign catalog / connection identifier (non-secret):**
- **Processing catalog and layer schemas:**
- **Volume path:**
- **Notebook paths and job definition version:**
- **Dashboard / alert / warehouse IDs:**
- **Validation run IDs and results:**
- **Known limitations / deviations:**
- **Cost guardrails and cleanup owner:**
- **Evidence location:**

Do not populate this template with invented deployment details. The original workspace is decommissioned; a new deployment record should be completed only after the environment is actually recreated.
