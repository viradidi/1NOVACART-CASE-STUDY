# NovaCart Data Dictionary

This document describes the source entities and the documented analytical outputs in the NovaCart case study. Confirm exact column names and data types against the SQL scripts and notebooks before deploying to a new environment.

## Source entities

### Products

| Attribute | Meaning | Notes |
|---|---|---|
| `product_id` | Product identifier | Primary key |
| `product_name` | Product display name | Source attribute |
| `category` | Product category | Used for category-level analysis |
| `price` | Product price | Defined as `VARCHAR(30)` in the supplied source DDL; locale-aware parsing handles US thousands separators and decimal-comma formats, then validates before numeric calculations |
| `updated_at` | Last source update timestamp | Used for incremental change detection |

### Orders

| Attribute | Meaning | Notes |
|---|---|---|
| `order_id` | Order identifier | Primary key |
| `customer_id` | Customer identifier | Avoid exposing real customer data in public examples |
| `product_id` | Related product identifier | Foreign key to products |
| `order_status` | Current order status | Define allowed values and handling of unknown values |
| `order_amount` | Order amount | Defined as `VARCHAR(30)` in the supplied source DDL; locale-aware parsing handles US thousands separators and decimal-comma formats, then validates before aggregation |
| `created_at` | Order creation timestamp | Business event time |
| `updated_at` | Last source update timestamp | Used for incremental change detection |

### Payments

| Attribute | Meaning | Notes |
|---|---|---|
| `payment_id` | Payment identifier | Primary key |
| `order_id` | Related order identifier | Foreign key to orders |
| `payment_status` | Payment status | Define success/failure/pending status mapping explicitly |
| `paid_amount` | Payment amount | Locale-aware parsing handles US thousands separators and decimal-comma formats; invalid strings become null and are quarantined |
| `processed_at` | Payment processing timestamp | Source change timestamp documented in the source DDL |

## Layered data model

### Bronze

Purpose: retain ingested source records and ingestion metadata for traceability.

Documented design elements include source-specific incremental tracking and an ingestion control table. The exact table names and columns should be taken from `bronze_work.ipynb` and the saved notebook definitions when recreating the environment.

### Silver

Purpose: prepare consistent, validated records for business transformations.

The documented workflow includes cleansing, standardization, deduplication, data-quality handling, and incremental Delta `MERGE` operations. Record the exact accepted/rejected rules and table schemas from the notebook implementation before treating them as a production contract.

### Gold

| Dataset | Grain / intent | Important considerations |
|---|---|---|
| `orders_information` | Current-state order-level analytics | Joins order, product and payment context; validate how multiple payments per order are aggregated |
| `orders_information_scd2` | Historical versions of selected order attributes | Validate business key, tracked attributes, effective/current-row semantics, and change detection |
| `category_performance` | Category-level performance aggregates | Validate category assignment, aggregation grain, and metric definitions |
| Volume snapshots | Latest and timestamped Parquet exports | Validate paths, retention, schema compatibility, and consumers |

## Analytical grain and join contracts

The grain is the first rule to establish before joining or aggregating. A correct-looking total can still be wrong if a one-to-many relationship multiplies rows.

| Entity / dataset | Declared grain | Key relationship | Modeling rule |
|---|---|---|---|
| Source products | One row per product | product_id | Product category and price are product attributes; a category change can affect order aggregates when Gold uses current product state |
| Source orders | One row per order | order_id; references product_id | The order is the central business entity in the order-level Gold output |
| Source payments | One row per payment record/attempt | payment_id; references order_id | Multiple payment records may belong to one order; aggregate or select a defined payment record before joining to order grain |
| Gold orders_information | One row per order | order_id | Payment data is summarized to order grain before the join; latest-payment attributes are descriptive, not payment-history measures |
| Gold orders_information_scd2 | One row per order version | Business key plus effective version interval | Historical versions must not be counted as separate current orders |
| Gold category_performance | One row per reporting category | Category key | Recompute all affected categories, including old and new categories after a product reclassification |

**Join safety:** Before joining, state the expected cardinality (one-to-one, many-to-one, or one-to-many), check key uniqueness on the relevant side, and compare row counts before and after the join. Do not join raw payment rows directly to order rows when the desired output is one row per order.

**Time semantics:** Source created_at is order business-event time; updated_at is the configured order/product change cursor; processed_at is the configured payment cursor. These are not interchangeable. Bronze also records ingestion time, and Silver/Gold control tables record processing progress. Keep source event time, source modification time, ingestion time, and pipeline processing time distinct in analysis.

## Processing-control schemas

The following are the control-table columns declared in the notebooks. They are operational metadata, not business facts.

### Bronze: bronze_schema.ingestion_control

| Column | Meaning |
|---|---|
| layer | Processing layer identifier |
| table_name | Source entity being ingested |
| ts_col / pk_col | Configured source timestamp and primary-key column names |
| last_successful_ts / last_successful_pk | Last successful composite source cursor |
| last_run_id | Identifier for the Bronze run |
| rows_written | Number of rows written by the recorded run |
| run_status | Run outcome used when selecting the successful cursor |
| updated_at | Control-record update time |

### Silver: silver_schema.processing_control

| Column | Meaning |
|---|---|
| layer / entity_name | Layer and entity being processed |
| last_processed_bronze_run_id | Latest Bronze run acknowledged by Silver |
| last_processed_bronze_ingested_at | Bronze ingestion-time boundary used by the Silver incremental read |
| rows_merged | Number of rows merged by the Silver run |
| run_status | Silver run outcome |
| silver_run_id | Identifier for the Silver run |
| updated_at | Silver control-record update time |

### Gold: gold_schema.processing_control

| Column | Meaning |
|---|---|
| layer / entity_name | Layer and entity being processed |
| last_processed_silver_run_id | Latest Silver run acknowledged by Gold |
| last_processed_silver_run_ts | Silver control timestamp used to discover unprocessed Silver runs |
| rows_merged | Number of Gold rows merged by the run |
| run_status | Gold run outcome |
| gold_run_id | Identifier for the Gold run |
| updated_at | Gold control-record update time |

The notebooks use separate entity progress for orders, products, and payments in Gold. A run ID identifies a processing attempt; it is not a source business key. The control tables should be inspected alongside target data when diagnosing a partial failure.

## Source-to-layer naming and audit fields

- Bronze source tables follow the <entity>_raw naming pattern in bronze_schema (for example, orders_raw).
- Silver current-state targets include orders_transformed, products_transformed, and payments_transformed in silver_schema.
- Bronze records ingestion metadata, including a Bronze run identifier and ingestion timestamp, to support traceability and incremental handoff.
- Silver records a Silver run identifier on processed current-state rows so Gold can identify rows associated with unprocessed Silver runs.
- Confirm exact audit-column spellings and complete target schemas against the notebook definitions when provisioning; this dictionary intentionally does not invent unverified target columns.
## Business metric definitions

The current Gold notebook implements the following definitions. Treat the status vocabulary and reporting grain as explicit business rules when presenting the metrics.

| Metric | Implemented definition |
|---|---|
| Total orders | Distinct order count at the one-row-per-order Gold grain |
| GMV | Sum of positive `order_amount` values; the current logic does not exclude cancelled orders by status |
| Paid amount | Sum of valid payment amounts whose normalized status is one of `PAID`, `SUCCESS`, `SUCCEEDED`, `SUCCESSFUL`, `COMPLETED`, or `SETTLED`; multiple successful payment records are summed per order |
| Order payment completion | `paid_amount / order_amount` when order amount is positive; otherwise zero |
| Average payment completion | Average of the per-order completion ratio within each category (an unweighted average of order ratios) |
| Payment failure rate | Payment-grain count of normalized `FAILED` records divided by all payment records joined to orders and products in the category; pending and other non-`FAILED` statuses remain in the denominator |

Do not use metric labels interchangeably. In particular, the average of per-order completion ratios is not generally equal to `SUM(paid_amount) / SUM(order_amount)`. Refunds, partial-payment reversals, and statuses outside the explicit success/failure vocabulary need a separate business rule before inclusion.

## Incremental processing metadata

The documented design tracks progress with timestamp and primary-key information, and stores processing metadata for downstream work. Before deployment, document the exact control-table schema from the notebooks, including:

- Entity/table name and source timestamp/key columns.
- Last successful timestamp and key (if both are used).
- Run identifier and run status.
- Rows read/written/merged, where recorded.
- When checkpoints advance and how failed runs resume.
- How timestamp ties, late updates, deletes, and null timestamps are handled.

For each entity, ensure the selected watermark field matches its source semantics. In particular, the source DDL identifies `payments.processed_at` as a timestamp; verify how that field is mapped through Silver and used by Gold rather than assuming that every entity has the same timestamp column.

## Data-quality checks to document

Recommended checks to map to the implemented transformations:

- Primary-key uniqueness in each current-state entity.
- Referential integrity from orders to products and payments to orders.
- Valid numeric conversion for amount and price fields.
- Required-field and null checks.
- Accepted status values.
- Duplicate and late-arriving record behavior.
- Non-negative/valid amounts according to business rules.
- Source-to-target counts and financial reconciliation.
- Gold aggregate reconciliation against the underlying order/payment population.

This list is a documentation and validation checklist, not a claim that every check is currently automated.

## Schema change management

When a source column or type changes:

1. Review the source DDL and affected notebooks.
2. Decide whether the change is compatible or requires a migration.
3. Update transformations and data-quality checks.
4. Test initial and incremental processing with representative data.
5. Confirm Gold metrics and dashboard queries remain valid.
6. Document the change and redeployment steps.

## Data privacy

Use synthetic or approved sample data for public screenshots and examples. Do not publish credentials, access tokens, personal customer data, or production payment details in this repository.
