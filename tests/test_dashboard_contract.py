import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "NovaCart Sales & Payments Overview.lvdash.json"


class DashboardContractTests(unittest.TestCase):
    def setUp(self):
        self.dashboard = json.loads(DASHBOARD.read_text(encoding="utf-8"))

    def test_category_dataset_exposes_business_metrics(self):
        dataset = next(item for item in self.dashboard["datasets"] if item["displayName"] == "category_performance")
        dimensions = {item["expr"] for item in dataset["config"]["dimensions"]}
        measures = {item["name"] for item in dataset["config"]["measures"]}
        self.assertIn("category", dimensions)
        self.assertTrue({
            "total_orders",
            "gmv",
            "total_paid",
            "average_payment_completion_ratio",
            "payment_failure_rate",
        }.issubset(measures))
        self.assertNotEqual(measures, {"count"})

    def test_category_table_references_declared_dataset_fields(self):
        dataset = next(item for item in self.dashboard["datasets"] if item["displayName"] == "category_performance")
        declared_dimensions = {item["expr"] for item in dataset["config"]["dimensions"]}
        declared_measures = {
            "total_orders",
            "Gross_Merchandise_Value",
            "Total_Paid_Amount",
            "Average_Payment_Completion_Ratio",
            "Payment_Failure_Rate",
        }
        table = next(
            item["widget"]
            for page in self.dashboard["pages"]
            for item in page["layout"]
            if item.get("widget", {}).get("name") == "cat_table"
        )
        fields = {field["name"] for field in table["queries"][0]["query"]["fields"]}
        self.assertIn("category", declared_dimensions)
        self.assertTrue(declared_measures.issubset(fields))


if __name__ == "__main__":
    unittest.main()
