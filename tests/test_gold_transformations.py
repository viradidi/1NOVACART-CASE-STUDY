import unittest

from pyspark.sql import SparkSession

from novacart_transformations import (
    aggregate_payments_by_order,
    calculate_category_metrics,
    clean_order_batch,
    clean_product_batch,
    clean_payment_batch,
    select_incremental_source_rows,
)


class NovaCartGoldTransformationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (
            SparkSession.builder
            .master("local[2]")
            .appName("NovaCartTransformationTests")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
        cls.spark.sparkContext.setLogLevel("ERROR")

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def test_bronze_cursor_includes_greater_keys_at_equal_timestamp(self):
        source = self.spark.createDataFrame(
            [
                (1, "2026-01-01 10:00:00"),
                (2, "2026-01-01 10:00:00"),
                (3, "2026-01-01 10:00:00"),
                (1, "2026-01-01 10:01:00"),
            ],
            ["source_id", "updated_at"],
        ).withColumn("updated_at", __import__("pyspark.sql.functions", fromlist=["col"]).col("updated_at").cast("timestamp"))
        selected = select_incremental_source_rows(
            source, "source_id", "updated_at", "2026-01-01 10:00:00", 2
        )
        self.assertEqual({row["source_id"] for row in selected.collect()}, {1, 3})

    def test_order_cleaning_deduplicates_and_quarantines_invalid_rows(self):
        source = self.spark.createDataFrame(
            [
                ("o-1", "c-1", "x", "new", "$10.00", "2026-01-01 10:00:00", "2026-01-02 10:00:00", "2026-01-02 10:01:00"),
                ("o-1", "c-1", "x", " shipped ", "$1,234.50", "2026-01-01 10:00:00", "2026-01-03 10:00:00", "2026-01-03 10:01:00"),
                ("o-2", None, "y", "pending", "??", "2026-01-01 10:00:00", "2026-01-03 10:00:00", "2026-01-03 10:01:00"),
            ],
            ["order_id", "customer_id", "product_id", "order_status", "order_amount", "created_at", "updated_at", "bronze_ingested_at"],
        )
        cleaned, good, bad = clean_order_batch(source, "silver-test")
        self.assertEqual(cleaned.count(), 2)
        self.assertEqual(good.count(), 1)
        self.assertEqual(bad.count(), 1)
        row = good.first()
        self.assertEqual(row["order_status"], "SHIPPED")
        self.assertEqual(row["order_amount"], 1234.5)
        self.assertEqual(row["silver_run_id"], "silver-test")

    def test_product_cleaning_standardizes_values_and_quarantines_bad_price(self):
        source = self.spark.createDataFrame(
            [
                ("p-1", "  phone-case ", "electrnics", "$1,299.99", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
                ("p-2", "bad product", "lifestyle", "not-a-price", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
            ],
            ["product_id", "product_name", "category", "price", "updated_at", "bronze_ingested_at"],
        )
        cleaned, good, bad = clean_product_batch(source, "silver-test")
        self.assertEqual(cleaned.count(), 2)
        self.assertEqual(good.count(), 1)
        self.assertEqual(bad.count(), 1)
        row = good.first()
        self.assertEqual(row["product_name"], "PHONE CASE")
        self.assertEqual(row["category"], "ELECTRONICS")
        self.assertEqual(row["price"], 1299.99)

    def test_payment_cleaning_normalizes_status_and_quarantines_missing_order(self):
        source = self.spark.createDataFrame(
            [
                ("pay-1", "o-1", " paid ", "$20.00", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
                ("pay-2", None, "failed", "15.00", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
            ],
            ["payment_id", "order_id", "payment_status", "paid_amount", "processed_at", "bronze_ingested_at"],
        )
        cleaned, good, bad = clean_payment_batch(source, "silver-test")
        self.assertEqual(cleaned.count(), 2)
        self.assertEqual(good.count(), 1)
        self.assertEqual(bad.count(), 1)
        row = good.first()
        self.assertEqual(row["payment_status"], "PAID")
        self.assertEqual(row["paid_amount"], 20.0)

    def test_payment_rollup_counts_only_successful_amounts_and_selects_latest(self):
        payments = self.spark.createDataFrame(
            [
                ("o-1", "p-1", "PAID", 40.0, "2026-01-01 10:00:00"),
                ("o-1", "p-2", "FAILED", 25.0, "2026-01-02 10:00:00"),
                ("o-1", "p-3", " settled ", 10.0, "2026-01-03 10:00:00"),
                ("o-2", "p-4", "PENDING", 99.0, "2026-01-01 10:00:00"),
            ],
            ["order_id", "payment_id", "payment_status", "paid_amount", "processed_at"],
        )

        rollup, latest = aggregate_payments_by_order(payments)
        paid = {row["order_id"]: row["paid_amount"] for row in rollup.collect()}
        latest_ids = {row["order_id"]: row["payment_id"] for row in latest.collect()}

        self.assertEqual(paid["o-1"], 50.0)
        self.assertEqual(paid["o-2"], 0.0)
        self.assertEqual(latest_ids["o-1"], "p-3")
        self.assertEqual(latest_ids["o-2"], "p-4")

    def test_category_metrics_use_order_and_payment_grains_and_find_empty_categories(self):
        gold_orders = self.spark.createDataFrame(
            [
                ("o-1", "A", 100.0, 50.0, 0.5),
                ("o-2", "A", 200.0, 200.0, 1.0),
                ("o-3", "B", 50.0, 0.0, 0.0),
            ],
            ["order_id", "category", "order_amount", "paid_amount", "payment_completion_ratio"],
        )
        silver_orders = self.spark.createDataFrame(
            [("o-1", "x"), ("o-2", "x"), ("o-3", "y")],
            ["order_id", "product_id"],
        )
        silver_products = self.spark.createDataFrame(
            [("x", "A"), ("y", "B")],
            ["product_id", "category"],
        )
        silver_payments = self.spark.createDataFrame(
            [
                ("o-1", "PAID"),
                ("o-1", "FAILED"),
                ("o-2", "PAID"),
                ("o-3", "PENDING"),
                ("o-3", "FAILED"),
            ],
            ["order_id", "payment_status"],
        )
        impacted = self.spark.createDataFrame([("A",), ("B",), ("C",)], ["category"])

        metrics, stale = calculate_category_metrics(
            gold_orders,
            silver_payments,
            silver_orders,
            silver_products,
            impacted,
        )
        actual = {row["category"]: row.asDict() for row in metrics.collect()}
        stale_categories = {row["category"] for row in stale.collect()}

        self.assertEqual(actual["A"]["total_orders"], 2)
        self.assertEqual(actual["A"]["Gross_Merchandise_Value"], 300.0)
        self.assertEqual(actual["A"]["Total_Paid_Amount"], 250.0)
        self.assertAlmostEqual(actual["A"]["Average_Payment_Completion_Ratio"], 0.75)
        self.assertAlmostEqual(actual["A"]["Payment_Failure_Rate"], 1 / 3)
        self.assertEqual(actual["B"]["total_orders"], 1)
        self.assertAlmostEqual(actual["B"]["Payment_Failure_Rate"], 0.5)
        self.assertEqual(stale_categories, {"C"})


if __name__ == "__main__":
    unittest.main()
