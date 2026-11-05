"""Reusable Spark transformations for NovaCart Gold business metrics."""

from pyspark.sql import Window
from pyspark.sql import functions as F


SUCCESSFUL_PAYMENT_STATUSES = (
    "PAID",
    "SUCCESS",
    "SUCCEEDED",
    "SUCCESSFUL",
    "COMPLETED",
    "SETTLED",
)


def _parse_numeric_amount(column_name: str):
    """Parse US thousands separators and decimal-comma amounts without inflation."""
    raw = F.regexp_replace(
        F.trim(F.col(column_name).cast("string")),
        r"[$€£\s]",
        "",
    )
    european_thousands_decimal = raw.rlike(r"^[+-]?\d{1,3}(?:\.\d{3})+,\d{1,2}$")
    decimal_comma = raw.rlike(r"^[+-]?\d+,\d{1,2}$")
    normalized = (
        F.when(
            european_thousands_decimal,
            F.regexp_replace(F.regexp_replace(raw, r"\.", ""), ",", "."),
        )
        .when(decimal_comma, F.regexp_replace(raw, ",", "."))
        .otherwise(F.regexp_replace(raw, ",", ""))
    )
    valid_numeric = normalized.rlike(r"^[+-]?\d+(?:\.\d+)?$")
    return F.when(valid_numeric, normalized.cast("double")).otherwise(F.lit(None).cast("double"))


def aggregate_payments_by_order(payments_df):
    """Return paid-amount rollup and deterministic latest payment descriptors."""
    payment_rollup = (
        payments_df
        .groupBy("order_id")
        .agg(
            F.sum(
                F.when(
                    F.upper(F.trim(F.col("payment_status"))).isin(*SUCCESSFUL_PAYMENT_STATUSES),
                    F.coalesce(F.col("paid_amount").cast("double"), F.lit(0.0)),
                ).otherwise(F.lit(0.0))
            ).alias("paid_amount"),
            F.max(F.col("processed_at").cast("timestamp")).alias("latest_payment_processed_at"),
        )
    )

    payment_window = Window.partitionBy("order_id").orderBy(
        F.col("processed_at").cast("timestamp").desc_nulls_last(),
        F.col("payment_id").cast("string").desc_nulls_last(),
    )
    latest_payment = (
        payments_df
        .withColumn("_payment_rank", F.row_number().over(payment_window))
        .filter(F.col("_payment_rank") == 1)
        .select(
            "order_id",
            "payment_id",
            F.col("payment_status").alias("payment_status"),
        )
    )
    return payment_rollup, latest_payment


def calculate_category_metrics(
    gold_orders_df,
    silver_payments_df,
    silver_orders_df,
    silver_products_df,
    impacted_categories_df,
):
    """Recompute impacted category metrics and identify categories now empty."""
    category_orders = (
        gold_orders_df
        .join(impacted_categories_df, "category", "inner")
        .groupBy("category")
        .agg(
            F.countDistinct("order_id").alias("total_orders"),
            F.sum(
                F.when(F.col("order_amount") > 0, F.col("order_amount"))
                .otherwise(F.lit(0.0))
            ).alias("Gross_Merchandise_Value"),
            F.sum(
                F.when(F.col("paid_amount") > 0, F.col("paid_amount"))
                .otherwise(F.lit(0.0))
            ).alias("Total_Paid_Amount"),
            F.avg(F.col("payment_completion_ratio")).alias("Average_Payment_Completion_Ratio"),
        )
    )

    payment_category_metrics = (
        silver_payments_df.alias("py")
        .join(silver_orders_df.alias("o"), "order_id", "inner")
        .join(
            silver_products_df.alias("p"),
            F.col("o.product_id") == F.col("p.product_id"),
            "inner",
        )
        .join(
            impacted_categories_df.alias("ic"),
            F.col("p.category") == F.col("ic.category"),
            "inner",
        )
        .groupBy(F.col("p.category").alias("category"))
        .agg(
            (
                F.sum(
                    F.when(
                        F.upper(F.trim(F.col("py.payment_status"))) == "FAILED",
                        1,
                    ).otherwise(0)
                )
                / F.count("*")
            ).alias("Payment_Failure_Rate")
        )
    )

    metrics = (
        category_orders
        .join(payment_category_metrics, "category", "left")
        .fillna({"Payment_Failure_Rate": 0.0})
    )

    active_categories = (
        gold_orders_df.select("category")
        .filter(F.col("category").isNotNull())
        .distinct()
    )
    stale_categories = (
        impacted_categories_df
        .join(active_categories, "category", "left_anti")
        .select("category")
    )
    return metrics, stale_categories


def clean_order_batch(orders_inc, silver_run_id):
    """Clean, deduplicate, validate, and split an incremental order batch."""
    order_window = Window.partitionBy("order_id").orderBy(
        F.col("updated_at").cast("timestamp").desc(),
        F.col("bronze_ingested_at").desc(),
    )
    cleaned = (
        orders_inc
        .withColumn("order_status", F.upper(F.trim(F.col("order_status"))))
        .withColumn("order_status", F.when(F.col("order_status") == "", F.lit(None)).otherwise(F.col("order_status")))
        .withColumn("order_amount", _parse_numeric_amount("order_amount"))
        .withColumn("created_at", F.to_timestamp("created_at"))
        .withColumn("updated_at", F.to_timestamp("updated_at"))
        .withColumn("row_rank", F.row_number().over(order_window))
        .filter(F.col("row_rank") == 1)
        .drop("row_rank")
        .withColumn("silver_run_id", F.lit(silver_run_id))
    )
    validated = (
        cleaned
        .withColumn(
            "to_be_verified_by_orders_team",
            F.when(F.col("customer_id").isNull(), "verify_customer_id")
            .when(F.col("product_id").isNull(), "verify_product_id")
            .when(F.col("order_status").isNull() | (F.trim(F.col("order_status")) == ""), "verify_order_status")
            .when(F.col("order_amount").isNull() | (F.col("order_amount") <= 0), "verify_order_amount")
            .otherwise("No Issues"),
        )
        .withColumn(
            "check_order_amount",
            F.when(F.col("order_amount").isNull() | (F.col("order_amount") <= 0), F.lit(True))
            .otherwise(F.lit(False)),
        )
        .withColumn("order_date", F.to_date("created_at"))
        .withColumn("order_year", F.year("created_at"))
        .withColumn("order_month", F.month("created_at"))
        .withColumn("order_day", F.dayofmonth("created_at"))
        .withColumn("order_dow", F.date_format("created_at", "E"))
    )
    good = validated.filter(F.col("to_be_verified_by_orders_team") == "No Issues")
    bad = validated.filter(F.col("to_be_verified_by_orders_team") != "No Issues").withColumn(
        "quarantine_ts", F.current_timestamp()
    )
    return cleaned, good, bad


def clean_product_batch(products_inc, silver_run_id):
    """Clean, deduplicate, validate, and split an incremental product batch."""
    product_window = Window.partitionBy("product_id").orderBy(
        F.col("updated_at").cast("timestamp").desc(),
        F.col("bronze_ingested_at").desc(),
    )
    cleaned = (
        products_inc
        .withColumn("product_name", F.upper(F.trim(F.col("product_name"))))
        .withColumn("product_name", F.regexp_replace(F.col("product_name"), r"[-_]", " "))
        .withColumn("product_name", F.when(F.col("product_name") == "", F.lit(None)).otherwise(F.col("product_name")))
        .withColumn(
            "category",
            F.when(F.upper(F.trim(F.col("category"))).contains("ELECTRNICS"), "ELECTRONICS")
            .when(F.upper(F.trim(F.col("category"))) == "FITNESS", "FITNESS")
            .when(F.upper(F.trim(F.col("category"))) == "LIFESTYLE", "LIFESTYLE")
            .otherwise(F.upper(F.trim(F.col("category")))),
        )
        .withColumn("price", _parse_numeric_amount("price"))
        .withColumn("updated_at", F.to_timestamp("updated_at"))
        .withColumn("row_rank", F.row_number().over(product_window))
        .filter(F.col("row_rank") == 1)
        .drop("row_rank")
        .withColumn("silver_run_id", F.lit(silver_run_id))
    )
    validated = (
        cleaned
        .withColumn(
            "to_be_verified_by_products_team",
            F.when(F.col("product_name").isNull(), "verify_product_name")
            .when(F.col("category").isNull(), "verify_category")
            .when(F.col("price").isNull() | (F.col("price") <= 0), "verify_price")
            .otherwise("No Issues"),
        )
        .withColumn(
            "check_product_price",
            F.when(F.col("price").isNull() | (F.col("price") <= 0), "invalid_price")
            .otherwise("valid_price"),
        )
    )
    good = validated.filter(
        (F.col("to_be_verified_by_products_team") == "No Issues")
        & (F.col("check_product_price") == "valid_price")
    )
    if "price_raw" in good.columns:
        good = good.drop("price_raw")
    bad = validated.filter(
        (F.col("to_be_verified_by_products_team") != "No Issues")
        | (F.col("check_product_price") == "invalid_price")
    ).withColumn("quarantine_ts", F.current_timestamp())
    return cleaned, good, bad


def clean_payment_batch(payments_inc, silver_run_id):
    """Clean, deduplicate, validate, and split an incremental payment batch."""
    payment_window = Window.partitionBy("payment_id").orderBy(
        F.col("processed_at").cast("timestamp").desc(),
        F.col("bronze_ingested_at").desc(),
    )
    cleaned = (
        payments_inc
        .withColumn("payment_status", F.upper(F.trim(F.col("payment_status"))))
        .withColumn("payment_status", F.when(F.col("payment_status") == "", F.lit(None)).otherwise(F.col("payment_status")))
        .withColumn("paid_amount", _parse_numeric_amount("paid_amount"))
        .withColumn("processed_at", F.to_timestamp("processed_at"))
        .withColumn("row_rank", F.row_number().over(payment_window))
        .filter(F.col("row_rank") == 1)
        .drop("row_rank")
        .withColumn("silver_run_id", F.lit(silver_run_id))
    )
    validated = (
        cleaned
        .withColumn(
            "to_be_verified_by_payments_team",
            F.when(F.col("order_id").isNull(), "verify_order_id")
            .when(F.col("payment_status").isNull(), "verify_payment_status")
            .when(F.col("paid_amount").isNull() | (F.col("paid_amount") <= 0), "verify_paid_amount")
            .otherwise("No Issues"),
        )
        .withColumn(
            "check_paid_amount",
            F.when(F.col("paid_amount").isNull() | (F.col("paid_amount") <= 0), F.lit(True))
            .otherwise(F.lit(False)),
        )
    )
    good = validated.filter(F.col("to_be_verified_by_payments_team") == "No Issues")
    bad = validated.filter(F.col("to_be_verified_by_payments_team") != "No Issues").withColumn(
        "quarantine_ts", F.current_timestamp()
    )
    return cleaned, good, bad


def select_incremental_source_rows(source_df, primary_key_column, timestamp_column, last_successful_ts, last_successful_pk):
    """Apply NovaCart's deterministic timestamp-plus-primary-key cursor boundary."""
    if last_successful_ts is None:
        return source_df
    if last_successful_pk is None:
        return source_df.filter(F.col(timestamp_column) > F.lit(last_successful_ts))
    return source_df.filter(
        (F.col(timestamp_column) > F.lit(last_successful_ts))
        | (
            (F.col(timestamp_column) == F.lit(last_successful_ts))
            & (F.col(primary_key_column).cast("long") > F.lit(int(last_successful_pk)))
        )
    )
