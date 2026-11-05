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
