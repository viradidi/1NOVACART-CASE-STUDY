import json
import unittest
from pathlib import Path

from deployment.render_novacart_job import render_job


ROOT = Path(__file__).resolve().parents[1]


class RenderNovaCartJobTests(unittest.TestCase):
    def setUp(self):
        self.template = json.loads((ROOT / "novacart_job.json").read_text(encoding="utf-8"))

    def test_renders_workspace_paths_and_resource_ids(self):
        result = render_job(
            self.template,
            "/Workspace/Shared/NovaCart",
            "dashboard-123",
            "alert-456",
            "warehouse-789",
        )
        tasks = {task["task_key"]: task for task in result["tasks"]}
        self.assertEqual(
            tasks["bronze_work"]["notebook_task"]["notebook_path"],
            "/Workspace/Shared/NovaCart/bronze_work",
        )
        self.assertEqual(
            tasks["silver_work"]["notebook_task"]["notebook_path"],
            "/Workspace/Shared/NovaCart/silver_work",
        )
        self.assertEqual(
            tasks["gold_work"]["notebook_task"]["notebook_path"],
            "/Workspace/Shared/NovaCart/gold_work",
        )
        self.assertEqual(tasks["novacart_dashboard"]["dashboard_task"]["dashboard_id"], "dashboard-123")
        self.assertEqual(tasks["n_alert"]["sql_task"]["alert"]["alert_id"], "alert-456")
        self.assertEqual(tasks["n_alert"]["sql_task"]["warehouse_id"], "warehouse-789")
        self.assertEqual(result["max_concurrent_runs"], 1)

    def test_rejects_missing_resource_ids(self):
        with self.assertRaises(ValueError):
            render_job(self.template, "/Workspace/Shared/NovaCart", "", "alert", "warehouse")

    def test_rejects_relative_workspace_root(self):
        with self.assertRaises(ValueError):
            render_job(self.template, "Workspace/Shared/NovaCart", "d", "a", "w")

    def test_does_not_mutate_template(self):
        before = json.dumps(self.template, sort_keys=True)
        render_job(self.template, "/Workspace/Shared/NovaCart", "d", "a", "w")
        self.assertEqual(json.dumps(self.template, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
