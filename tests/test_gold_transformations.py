import unittest
from datetime import datetime

from pyspark.sql import SparkSession, functions as F

from novacart_transformations import (
    aggregate_payments_by_order,
    calculate_category_metrics,
    clean_order_batch,
    clean_product_batch,
    clean_payment_batch,
    select_incremental_source_rows,
    derive_impacted_categories,
    normalize_source_timestamp,
    find_invalid_cursor_rows,
    format_snapshot_run_path,
    find_scd2_current_duplicates,
    find_gold_orders_missing_current_scd2,
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

    def test_bronze_rejects_null_cursor_fields_before_watermark_filtering(self):
        source = self.spark.createDataFrame(
            [
                (1, "2026-01-01 10:00:00"),
                (2, None),
                (None, "2026-01-01 10:01:00"),
            ],
            ["source_id", "updated_at"],
        ).withColumn("updated_at", F.col("updated_at").cast("timestamp"))
        invalid = find_invalid_cursor_rows(source, "source_id", "updated_at")
        self.assertEqual(invalid.count(), 2)

    def test_bronze_timestamp_normalization_truncates_to_milliseconds(self):
        source = self.spark.createDataFrame(
            [("2026-01-01 10:00:00.123456",), ("2026-01-01 10:00:00.999999",)],
            ["updated_at"],
        )
        normalized = normalize_source_timestamp(source, "updated_at")
        values = sorted(row["updated_at"].strftime("%H:%M:%S.%f") for row in normalized.collect())
        self.assertEqual(values, ["10:00:00.123000", "10:00:00.999000"])

    def test_impacted_categories_survive_retry_after_current_gold_merge(self):
        current_gold_after_merge = self.spark.createDataFrame(
            [("o-1", "NEW_CATEGORY")],
            ["order_id", "category"],
        )
        gold_delta = self.spark.createDataFrame(
            [("o-1", "NEW_CATEGORY")],
            ["order_id", "category"],
        )
        impacted_orders = self.spark.createDataFrame([("o-1",)], ["order_id"])
        scd2_history = self.spark.createDataFrame(
            [
                ("o-1", "OLD_CATEGORY", False),
                ("o-1", "NEW_CATEGORY", True),
            ],
            ["order_id", "category", "is_current"],
        )
        actual = {
            row["category"]
            for row in derive_impacted_categories(
                current_gold_after_merge,
                gold_delta,
                impacted_orders,
                scd2_history,
            ).collect()
        }
        self.assertEqual(actual, {"OLD_CATEGORY", "NEW_CATEGORY"})

    def test_scd2_integrity_checks_detect_duplicate_current_and_missing_history(self):
        history = self.spark.createDataFrame(
            [
                ("o-1", True),
                ("o-1", False),
                ("o-2", True),
                ("o-2", True),
            ],
            ["order_id", "is_current"],
        )
        gold = self.spark.createDataFrame(
            [("o-1",), ("o-2",), ("o-3",)],
            ["order_id"],
        )
        duplicates = {
            row["order_id"]
            for row in find_scd2_current_duplicates(history).collect()
        }
        missing = {
            row["order_id"]
            for row in find_gold_orders_missing_current_scd2(gold, history).collect()
        }
        self.assertEqual(duplicates, {"o-2"})
        self.assertEqual(missing, {"o-3"})

    def test_gold_snapshot_path_is_filesystem_safe_and_unique_per_run(self):
        started = datetime(2026, 11, 5, 12, 55, 30, 123456)
        first = format_snapshot_run_path(started, "12345678-aaaa")
        second = format_snapshot_run_path(started, "87654321-bbbb")
        self.assertNotEqual(first, second)
        self.assertIn("2026-11-05T12-55-30.123456Z", first)
        self.assertNotIn(":", first)

    def test_bronze_cursor_includes_greater_keys_at_equal_timestamp(self):
        source = self.spark.createDataFrame(
            [
                (1, "2026-01-01 10:00:00"),
                (2, "2026-01-01 10:00:00"),
                (3, "2026-01-01 10:00:00"),
                (1, "2026-01-01 10:01:00"),
            ],
            ["source_id", "updated_at"],
        ).withColumn("updated_at", F.col("updated_at").cast("timestamp"))
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
                ("o-3", "c-3", "z", "placed", "50,00", "2026-01-01 10:00:00", "2026-01-03 10:00:00", "2026-01-03 10:01:00"),
            ],
            ["order_id", "customer_id", "product_id", "order_status", "order_amount", "created_at", "updated_at", "bronze_ingested_at"],
        )
        cleaned, good, bad = clean_order_batch(source, "silver-test")
        self.assertEqual(cleaned.count(), 3)
        self.assertEqual(good.count(), 2)
        self.assertEqual(bad.count(), 1)
        row = good.filter(F.col("order_id") == "o-1").first()
        decimal_comma_row = good.filter(F.col("order_id") == "o-3").first()
        self.assertEqual(row["order_status"], "SHIPPED")
        self.assertEqual(row["order_amount"], 1234.5)
        self.assertEqual(decimal_comma_row["order_amount"], 50.0)
        self.assertEqual(row["silver_run_id"], "silver-test")
        first_quarantine_id = bad.first()["quarantine_id"]
        _, _, retry_bad = clean_order_batch(source, "silver-test")
        self.assertEqual(retry_bad.first()["quarantine_id"], first_quarantine_id)
        self.assertEqual(len(first_quarantine_id), 64)

    def test_product_cleaning_standardizes_values_and_quarantines_bad_price(self):
        source = self.spark.createDataFrame(
            [
                ("p-1", "  phone-case ", "electrnics", "$1,299.99", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
                ("p-2", "bad product", "lifestyle", "not-a-price", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
                ("p-3", "decimal-price", "fitness", "15,00", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
            ],
            ["product_id", "product_name", "category", "price", "updated_at", "bronze_ingested_at"],
        )
        cleaned, good, bad = clean_product_batch(source, "silver-test")
        self.assertEqual(cleaned.count(), 3)
        self.assertEqual(good.count(), 2)
        self.assertEqual(bad.count(), 1)
        row = good.filter(F.col("product_id") == "p-1").first()
        decimal_comma_row = good.filter(F.col("product_id") == "p-3").first()
        self.assertEqual(row["product_name"], "PHONE CASE")
        self.assertEqual(row["category"], "ELECTRONICS")
        self.assertEqual(row["price"], 1299.99)
        self.assertEqual(decimal_comma_row["price"], 15.0)
        self.assertEqual(len(bad.first()["quarantine_id"]), 64)

    def test_payment_cleaning_normalizes_status_and_quarantines_missing_order(self):
        source = self.spark.createDataFrame(
            [
                ("pay-1", "o-1", " paid ", "$20.00", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
                ("pay-2", None, "failed", "15.00", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
                ("pay-3", "o-3", "PAID", "100,00", "2026-01-01 10:00:00", "2026-01-01 10:01:00"),
            ],
            ["payment_id", "order_id", "payment_status", "paid_amount", "processed_at", "bronze_ingested_at"],
        )
        cleaned, good, bad = clean_payment_batch(source, "silver-test")
        self.assertEqual(cleaned.count(), 3)
        self.assertEqual(good.count(), 2)
        self.assertEqual(bad.count(), 1)
        row = good.filter(F.col("payment_id") == "pay-1").first()
        decimal_comma_row = good.filter(F.col("payment_id") == "pay-3").first()
        self.assertEqual(row["payment_status"], "PAID")
        self.assertEqual(row["paid_amount"], 20.0)
        self.assertEqual(decimal_comma_row["paid_amount"], 100.0)
        self.assertEqual(len(bad.first()["quarantine_id"]), 64)

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
        attempts = self.spark.createDataFrame(
            [
                ("o-1", "p-1", "PAID", 40.0, "2026-01-01 10:00:00"),
                ("o-1", "p-2", "FAILED", 25.0, "2026-01-02 10:00:00"),
                ("o-1", "p-3", "SETTLED", 10.0, "2026-01-03 10:00:00"),
                ("o-1", "p-5", "FAILED", None, "2026-01-04 10:00:00"),
                ("o-2", "p-4", "PENDING", 99.0, "2026-01-01 10:00:00"),
            ],
            ["order_id", "payment_id", "payment_status", "paid_amount", "processed_at"],
        )

        rollup, latest = aggregate_payments_by_order(payments, attempts)
        paid = {row["order_id"]: row["paid_amount"] for row in rollup.collect()}
        latest_by_order = {row["order_id"]: row.asDict() for row in latest.collect()}

        self.assertEqual(paid["o-1"], 50.0)
        self.assertEqual(paid["o-2"], 0.0)
        self.assertEqual(latest_by_order["o-1"]["payment_id"], "p-5")
        self.assertEqual(latest_by_order["o-1"]["payment_status"], "FAILED")
        self.assertEqual(
            str(latest_by_order["o-1"]["latest_payment_processed_at"]),
            "2026-01-04 10:00:00",
        )
        self.assertEqual(latest_by_order["o-2"]["payment_id"], "p-4")

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
                # This failed attempt has a malformed amount and is absent from
                # the valid payment table, but remains in the cleaned attempt feed.
                ("o-2", "FAILED"),
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
        self.assertAlmostEqual(actual["A"]["Payment_Failure_Rate"], 0.5)
        self.assertEqual(actual["B"]["total_orders"], 1)
        self.assertAlmostEqual(actual["B"]["Payment_Failure_Rate"], 0.5)
        self.assertEqual(stale_categories, {"C"})


if __name__ == "__main__":
    unittest.main()
