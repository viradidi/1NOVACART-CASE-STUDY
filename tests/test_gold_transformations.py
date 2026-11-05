import unittest

from pyspark.sql import SparkSession

from novacart_transformations import (
    aggregate_payments_by_order,
    calculate_category_metrics,
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
