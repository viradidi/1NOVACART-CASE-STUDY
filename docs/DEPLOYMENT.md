# NovaCart Deployment Guide

This guide explains how to recreate the NovaCart case-study environment from the artifacts in this repository.

> **Project status: WORKING IMPLEMENTATION.** NovaCart was implemented and run in its original Azure Databricks environment. That workspace was later deleted to control costs, so the project is not currently hosted. This guide covers restoring the cloud environment if a live demonstration or regression run is needed. Cloud resource names, IDs, permissions, networking, and credentials must be configured for the target environment.

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

## 7. Import and run the notebooks

Import the three notebook files into the target workspace. Update their source references and configuration first.

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
