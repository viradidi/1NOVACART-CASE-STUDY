# NovaCart Engineering Decisions

This document records the important design choices represented by the NovaCart notebooks and saved job configuration. It distinguishes documented design intent from guarantees that still need to be validated in a newly deployed environment.

## 1. Layered Bronze, Silver, and Gold processing

**Decision:** Separate source ingestion, data preparation, and business-facing transformations into layers.

**Why it helps**
- Bronze preserves ingested source records and ingestion metadata for investigation.
- Silver centralizes cleansing, standardization, deduplication, and data-quality handling.
- Gold presents datasets shaped for reporting and business questions.
- A layer boundary makes responsibilities and failures easier to reason about.

**Trade-offs**
- Additional tables and orchestration steps increase storage and operational complexity.
- Schema or logic changes must be coordinated across layers.
- Data latency includes the time required to process each stage.

**Validation evidence to capture**
- Show one representative record moving from source through Bronze and Silver to Gold.
- Record row counts and the rules used to explain expected differences between layers.
- Demonstrate how a rejected or malformed record is handled, if quarantine logic is implemented.

## 2. Lakehouse Federation for source access

**Decision:** Use Databricks Lakehouse Federation to access Azure SQL tables rather than relying on a conventional extract connector for this source-access path.

**Why it helps**
- Reduces the need to build and operate a separate extraction mechanism for the federated access path.
- Provides a governed way to access supported external data sources from Databricks.
- Can simplify development where the workload is suitable for federated queries.

**Trade-offs**
- Query performance and availability depend partly on the external database and connectivity.
- Source workload and network latency remain relevant.
- Federation is not equivalent to a durable ingestion copy; downstream processing still needs appropriate state and storage behavior.

**Validation evidence to capture**
- Show the configured connection and successful reads without exposing credentials.
- Document permissions, networking, and the tested source-query behavior.
- Measure or describe source impact before scaling query volume.

## 3. Incremental ingestion and watermarks

**Decision:** Track processing progress using source timestamp and primary-key information, with control metadata for ingestion runs.

**Why it helps**
- Reduces unnecessary rereading of unchanged source data.
- Makes the last successful processing position explicit.
- Supports repeatable incremental runs when checkpoint advancement is coordinated with successful writes.

**Trade-offs and failure modes**
- Multiple rows can share a timestamp; a timestamp-only boundary can miss or reread records depending on comparison logic.
- Updates with old timestamps and late-arriving records can fall behind a watermark.
- A checkpoint advanced before a durable write can cause data loss after failure.
- A checkpoint advanced after a write can cause rereads; downstream idempotency is needed to make those safe.
- Hard deletes require a separate strategy if the source query only returns currently existing rows.

**Engineering requirements**
- Define a deterministic ordering when timestamp and primary key are both used.
- Document inclusive/exclusive boundaries and tie handling.
- Advance the watermark only at the correct success boundary.
- Make retries safe, and add a lookback or reconciliation strategy where the source's change semantics require it.
- Test equal timestamps, late updates, and failures between data writes and checkpoint updates.

**Validation evidence to capture**
1. Run an initial load.
2. Run again with no changes and compare results.
3. Insert a new source row.
4. Update an existing row.
5. Create a timestamp tie or late update in a test dataset.
6. Interrupt a run at a controlled point if the environment permits, then verify safe recovery.

These are recommended tests, not a claim that every case has already been exercised.

## 4. Silver Delta MERGE

**Decision:** Use Delta Lake merge operations to update current-state Silver records rather than blindly appending every observed change as a new current row.

**Why it helps**
- Matches changed records by a business key.
- Supports inserts and updates in one transformation pattern.
- Can make reruns idempotent when source selection, keys, and merge conditions are deterministic.

**Trade-offs**
- Incorrect or non-unique merge keys can create ambiguous results or duplicate target records.
- Merge operations add compute and transaction overhead.
- Late updates and out-of-order source changes need explicit rules.
- A merge alone does not guarantee end-to-end exactly-once processing.

**Validation evidence to capture**
- Confirm one current Silver row per intended business key.
- Run the same input twice and verify no unintended row growth.
- Verify an update changes the expected attributes.
- Verify duplicate source keys are resolved or rejected deterministically before merge.

## 5. Gold processing based on changed entities

**Decision:** Recalculate affected order records and impacted categories instead of rebuilding every Gold output for every run.

**Why it helps**
- Can reduce repeated transformation work when only a small portion of the source changes.
- Makes the relationship between changed source entities and affected business outputs explicit.
- Supports targeted updates to current-state and aggregate tables.

**Trade-offs**
- Change-impact logic is more complex than a full refresh.
- A product change can affect many orders; a payment change can affect order and category metrics.
- Missing an affected key can leave Gold stale even when upstream tables are correct.
- A timestamp comparison that is inconsistent across entities can skip required updates.

**Engineering requirements**
- Identify impacted orders from order changes and payment changes.
- Identify orders affected by product changes through the relevant product-to-order relationship.
- Derive the complete impacted category set from affected records.
- Define what happens when an entity is deleted or changes category.
- Use periodic full reconciliation or a controlled full rebuild as a recovery option when practical.

**Validation evidence to capture**
- Change one order, one payment, and one product in isolated test cases.
- Confirm all affected Gold records and categories are refreshed.
- Compare the incremental result with a full recomputation on the same test data.

## 6. Current-state order model

**Decision:** Maintain an `orders_information` dataset that combines order context with related product and payment information.

**Why it helps**
- Simplifies common analytical queries by presenting relevant context together.
- Gives dashboard authors a clearer reporting surface than repeated joins across operational entities.

**Trade-offs**
- Join cardinality matters: multiple payment records per order can multiply order rows if aggregation rules are not explicit.
- Product attributes may change after an order is created; the model must define whether it reports current product attributes or order-time attributes.
- Monetary metrics require validated numeric types and documented treatment of refunds, partial payments, and invalid values.

**Validation evidence to capture**
- Confirm the dataset grain is one row per order if that is the intended contract.
- Test an order with multiple payment records.
- Reconcile a small hand-calculated sample against the resulting dataset.

## 7. SCD Type 2 history

**Decision:** Maintain an `orders_information_scd2` dataset to retain versions of selected order attributes when tracked values change.

**Why it helps**
- Preserves historical context rather than overwriting every prior state.
- Supports questions about how selected order attributes changed over time.

**Trade-offs**
- Increases storage and transformation complexity.
- Requires clear effective/current-row semantics and reliable change detection.
- Reprocessing the same input must not create duplicate historical versions.
- Late-arriving changes may require a defined correction policy for historical intervals.

**Validation evidence to capture**
- Insert a new order and confirm the initial version.
- Change a tracked attribute and confirm the prior version is closed and a new current version is created.
- Reprocess the same data and confirm no duplicate version appears.
- Confirm changes to non-tracked attributes follow the intended policy.

## 8. Incremental category aggregation

**Decision:** Update category-level performance metrics for categories affected by changed order, payment, or product data.

**Why it helps**
- Avoids recalculating all categories when only a subset is affected.
- Keeps business-oriented metrics available in a compact reporting table.

**Trade-offs**
- A changed product category can affect both the old and new categories.
- Deletions or records becoming ineligible may require subtracting their prior contribution.
- The definition of total orders, GMV, paid amount, completion, and failure rate must be stable and documented.
- Incremental aggregation can drift if impacted categories are missed.

**Engineering requirements**
- Determine affected categories using both prior and new values when a category can change.
- Make the aggregation grain explicit.
- Define zero-denominator, null, overpayment, refund, and status-handling policies.
- Compare incremental results with a full aggregation periodically or during validation.

## 9. Latest and timestamped Volume snapshots

**Decision:** Publish a latest snapshot and timestamped Parquet snapshots to a Databricks Volume.

**Why it helps**
- Provides a convenient export artifact for downstream consumers and demonstration workflows.
- Timestamped outputs can help retain a sequence of published states for comparison.

**Trade-offs**
- Snapshots consume storage and need retention rules.
- Consumers need to know whether a snapshot is complete and which run produced it.
- Replacing a latest snapshot must not expose a partially written result.
- Snapshot files should not be treated as a substitute for transactionally managed source tables.

**Validation evidence to capture**
- Confirm snapshot schema, path, and row count.
- Confirm that the latest output corresponds to the expected successful run.
- Define retention and cleanup behavior.

## 10. Sequential Databricks Job orchestration

**Decision:** Chain Bronze, Silver, Gold, dashboard, and alert tasks using successful-completion dependencies. The saved configuration sets `max_concurrent_runs` to `1`.

**Why it helps**
- Makes the intended processing order explicit.
- Prevents dependent tasks from running before their prerequisites succeed.
- Avoids overlapping job runs under the saved concurrency setting.

**Trade-offs**
- Sequential execution can increase end-to-end latency.
- A failure in an upstream task blocks downstream tasks until the failure is resolved or rerun.
- A saved JSON export contains workspace-specific paths and resource identifiers that need replacement in a new environment.

**Validation evidence to capture**
- Confirm task dependencies and notebook paths in the deployed job.
- Observe a successful run and a controlled failure.
- Confirm downstream tasks do not run when their prerequisite fails.
- Confirm failure notifications and rerun behavior.

## 11. Cost-conscious deployment

**Decision:** Preserve project artifacts in GitHub and decommission the cloud workspace when it is not needed for active demonstrations.

**Why it helps**
- Avoids keeping paid compute running solely for a portfolio.
- Makes the implementation and design reviewable without requiring a live cloud environment.

**Trade-offs**
- A reviewer cannot interact with a live workspace while it is decommissioned.
- Recreating resources takes time and may require new permissions, IDs, and configuration.
- Other separately provisioned cloud resources may still incur charges after a workspace is deleted.

**Engineering practice**
- Keep notebooks, SQL scripts, job/dashboard exports, documentation, and non-sensitive sample data under version control.
- Keep credentials out of the repository.
- Recreate the environment only for a planned validation or demonstration.
- Capture genuine test and dashboard evidence during that run.

## Summary

NovaCart demonstrates design patterns for layered data processing, incremental state, merge-based transformations, historical modeling, impacted-entity analytics, and scheduled orchestration. Their correctness depends on explicit data contracts, watermark semantics, idempotency, reconciliation, and recovery tests. The saved artifacts document the intended implementation; production-level guarantees should only be claimed when supported by repeatable evidence.
