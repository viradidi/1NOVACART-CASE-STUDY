# NovaCart Operations Runbook

This runbook describes how to investigate and recover common failures in a redeployed NovaCart environment. It is written as an operational checklist; validate the exact table names, job settings, and recovery behavior against the current notebooks before using it during a live incident.

> **Environment status:** The original Azure Databricks workspace was deleted to control costs. These procedures apply when the project is redeployed. No live workspace or running job is implied by this document.

## 1. Operational principles

1. Identify the failed task and run before changing data or checkpoints.
2. Preserve run IDs, error messages, relevant timestamps, and row counts.
3. Fix the underlying cause before retrying.
4. Prefer safe reruns of idempotent transformations over manual edits to target tables.
5. Do not advance a watermark manually unless the recovery plan and source/target reconciliation justify it.
6. Keep credentials and sensitive source data out of logs, screenshots, and GitHub issues.
7. After recovery, verify downstream outputs—not only a green job status.

## 2. First-response checklist

When a run fails:

- [ ] Identify the failed Databricks Job run and task.
- [ ] Capture the task error, start/end time, run identifier, and affected layer.
- [ ] Determine whether the task failed before writing, during a write, or after writing but before updating control metadata.
- [ ] Check whether upstream tasks completed successfully.
- [ ] Inspect relevant control-table state and target table changes.
- [ ] Check source connectivity, permissions, compute availability, and recent schema changes.
- [ ] Decide whether a retry is safe based on the actual write and checkpoint semantics.
- [ ] After retry, validate counts, keys, business metrics, and downstream outputs.

## 3. Source connection or federation failure

**Symptoms:** Bronze cannot read a source table, queries time out, or access is denied.

**Investigate**
1. Confirm the source database is available.
2. Confirm the target workspace has network access to Azure SQL.
3. Check the connection and authentication configuration using the approved Databricks interface.
4. Confirm the execution identity has read permissions on the required source objects.
5. Check for source-side schema or permission changes.

**Recovery**
- Restore connectivity or permissions through the approved identity and network process.
- Rerun the failed task after verifying the source is readable.
- Confirm the source query returns expected columns and a plausible row count.

Do not put passwords, tokens, or connection strings in notebook output or issue comments.

## 4. Bronze ingestion failure

**Symptoms:** Ingestion stops, the control record does not advance, or the target appears partially updated.

**Investigate**
- Check the run's source timestamp/key boundary and the previous successful checkpoint.
- Check whether any Bronze write committed before the failure.
- Compare target keys and counts against the source selection for the affected interval.
- Check type conversion, null timestamp, and schema errors.

**Recovery**
1. Correct the cause of the failure.
2. Determine from the notebook implementation whether the source interval can safely be reread.
3. If the writer is idempotent, rerun the affected task using its supported recovery path.
4. If the write/checkpoint outcome is uncertain, reconcile the affected interval before retrying.
5. Confirm the checkpoint only reflects successfully processed data.

Do not set the watermark to the current time merely to make the next run complete; this can skip source changes.

## 5. Watermark or late-arriving update concern

**Symptoms:** A source record changed but the downstream value did not update, or the same records appear repeatedly.

**Investigate**
- Verify the timestamp column used for that entity.
- Check whether the source timestamp is updated reliably for every relevant mutation.
- Inspect the comparison boundary, timestamp ties, and primary-key tie-break logic.
- Determine whether the change arrived with an older timestamp than the saved watermark.
- Compare the control table with the actual last successfully written source position.

**Recovery**
- Follow the notebook's supported lookback or backfill mechanism if one exists.
- If there is no safe automated mechanism, define a bounded reprocessing window and reconcile the affected keys before changing state.
- Document the correction and add a regression case for the failure mode.

A timestamp watermark cannot by itself detect every hard delete or every mutation that fails to update the timestamp. Those cases need an explicit source-change or reconciliation strategy.

## 6. Silver merge or data-quality failure

**Symptoms:** Merge errors, duplicate keys, unexpected nulls, type-cast failures, or rejected records increase.

**Investigate**
- Inspect the source rows for duplicate merge keys.
- Review the schema and type conversion for changed source values.
- Check the data-quality rules and the handling of rejected rows.
- Confirm the target table's key and merge condition.
- Determine whether any write committed before the failure.

**Recovery**
1. Correct the source or transformation issue.
2. Apply the documented duplicate-resolution or quarantine policy.
3. Rerun using the notebook's supported method.
4. Verify one current record per intended business key.
5. Compare rejected-row counts and sample records with the expected policy.

Do not delete or overwrite a Silver table as a first response. Preserve evidence and use a controlled rebuild only when required and understood.

## 7. Gold output is stale or incorrect

**Symptoms:** Dashboard metrics do not reflect a recent source change, category totals differ, or current-state orders are missing.

**Investigate**
- Confirm Bronze and Silver processed the source change.
- Inspect Gold processing-control state and the last successful run.
- Verify the changed source entity was included in the impacted order/category set.
- Check product category changes, payment changes, and orders with multiple payment records.
- Review the business definitions and numeric casting used for GMV, paid amount, completion, and failure rate.
- Compare incremental outputs with a full recomputation on a controlled dataset where practical.

**Recovery**
1. Correct the transformation or impacted-entity selection.
2. Reprocess affected entities using the documented approach.
3. Recalculate the affected category aggregates.
4. Reconcile the corrected results against source and Silver data.
5. Confirm dashboard queries return the corrected values.

If the impacted set cannot be established confidently, use a reviewed full rebuild or reconciliation path rather than guessing which rows to patch.

## 8. SCD Type 2 history issue

**Symptoms:** Multiple current versions exist, no new version appears after a tracked change, or reruns create duplicate history.

**Investigate**
- Confirm the intended business key and tracked columns.
- Inspect current-row/effective-time fields used by the implementation.
- Verify whether the prior version was closed and the new version inserted.
- Check whether the same input was processed more than once.
- Consider late-arriving changes and the policy for correcting historical intervals.

**Recovery**
- Pause downstream use if historical correctness is materially affected.
- Preserve the affected key's version history before making corrections.
- Apply a controlled correction based on the documented SCD logic.
- Rerun the relevant test cases and confirm exactly the intended current row and history.

Do not manually delete history rows without documenting the expected timeline and verifying the correction.

## 9. Dashboard or SQL alert failure

**Symptoms:** Dashboard queries fail, values appear stale, or an alert does not fire.

**Investigate**
- Confirm the Gold tables were updated successfully.
- Verify the dashboard dataset/query references, catalog/schema names, and SQL warehouse availability.
- Check alert condition, evaluation frequency, recipients, and permissions.
- Test the query independently before changing the alert.

**Recovery**
- Update stale resource references after confirming the intended target.
- Test the dashboard against known sample results.
- Test alert behavior with a controlled condition and approved recipient.
- Avoid sending repeated test notifications to real stakeholders.

## 10. Job dependency or scheduling failure

**Symptoms:** A downstream task is skipped, a task points to a missing notebook, or runs overlap unexpectedly.

**Investigate**
- Check the failed task and its upstream dependency outcomes.
- Verify notebook paths and task identifiers after deployment.
- Check permissions and compute configuration.
- Confirm concurrency, queuing, schedule, timeout, and notification settings.

**Recovery**
- Correct the configuration and run the workflow manually in dependency order.
- Verify the task chain is Bronze → Silver → Gold → dashboard → alert as intended.
- Re-enable the schedule only after the manual run and downstream checks succeed.

The saved job JSON contains old workspace-specific paths and resource IDs; these must be replaced during redeployment.

## 11. Snapshot publishing issue

**Symptoms:** No Parquet snapshot appears, a latest snapshot is stale, or downstream readers see an incomplete export.

**Investigate**
- Check the Gold task result and Volume permissions.
- Inspect the expected output path, file creation time, row count, and schema.
- Determine whether the failed write left partial or temporary output.
- Confirm which run should be considered the latest successful publication.

**Recovery**
- Correct the path or permissions.
- Use the notebook's supported publishing procedure to regenerate the output.
- Verify the snapshot before treating it as published.
- Apply a retention policy to timestamped snapshots; do not delete files until consumer and recovery requirements are understood.

## 12. Reconciliation checklist

After recovery, record and review:

- Source rows selected for the affected interval.
- Bronze rows written and control state.
- Silver key uniqueness, accepted/rejected rows, and merge results.
- Gold order-level outputs and affected category totals.
- Payment metrics against the agreed status and amount definitions.
- SCD Type 2 current-row and history behavior, if affected.
- Snapshot path and run association, if affected.
- Dashboard query results and alert behavior, if affected.
- Final job status and any remaining known issues.

Row counts alone are insufficient when updates, filtering, or aggregation change the number of rows. Pair counts with key-level and metric-level checks.

## 13. Incident record template

Use this template in an internal incident log. Do not include credentials or private customer data.

- **Date/time:**
- **Environment / job run ID:**
- **Failed task / layer:**
- **Observed symptom:**
- **Impact and affected datasets:**
- **Evidence collected:**
- **Root cause:**
- **Recovery action:**
- **Reconciliation performed:**
- **Final outcome:**
- **Follow-up test or preventive change:**

## 14. Recovery readiness

Before calling the workflow operationally ready, demonstrate that:
- Repeated runs do not create unintended duplicates.
- Checkpoints are advanced at the correct success boundary.
- A controlled failure can be diagnosed and retried safely.
- Late updates and timestamp ties are handled according to documented rules.
- Incremental Gold results reconcile with a full recomputation on test data.
- Alerting and run-history evidence are accessible to the responsible operator.

These are readiness criteria. They should only be marked complete after the corresponding tests have been run and evidence retained.
