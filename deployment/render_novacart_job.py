#!/usr/bin/env python3
"""Render a workspace-specific Databricks job JSON from the NovaCart template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PLACEHOLDERS = {
    "dashboard_id": "REPLACE_WITH_DASHBOARD_ID",
    "alert_id": "REPLACE_WITH_ALERT_ID",
    "warehouse_id": "REPLACE_WITH_WAREHOUSE_ID",
}


def render_job(
    template: dict[str, Any],
    workspace_root: str,
    dashboard_id: str,
    alert_id: str,
    warehouse_id: str,
) -> dict[str, Any]:
    """Return a validated job definition with target-workspace paths and IDs."""
    root = "/" + workspace_root.strip("/")
    if not root.startswith("/"):
        raise ValueError("workspace_root must be an absolute workspace path")
    if any(not value.strip() for value in (dashboard_id, alert_id, warehouse_id)):
        raise ValueError("dashboard_id, alert_id, and warehouse_id are required")

    rendered = json.loads(json.dumps(template))
    task_by_key = {task["task_key"]: task for task in rendered.get("tasks", [])}
    expected_tasks = {"bronze_work", "silver_work", "gold_work", "novacart_dashboard", "n_alert"}
    missing = expected_tasks - set(task_by_key)
    if missing:
        raise ValueError(f"Job template is missing tasks: {sorted(missing)}")

    for task_key in ("bronze_work", "silver_work", "gold_work"):
        notebook_task = task_by_key[task_key].get("notebook_task", {})
        notebook_task["notebook_path"] = f"{root}/{task_key}"
        notebook_task["source"] = "WORKSPACE"

    task_by_key["novacart_dashboard"].setdefault("dashboard_task", {})["dashboard_id"] = dashboard_id
    alert = task_by_key["n_alert"].setdefault("sql_task", {}).setdefault("alert", {})
    alert["alert_id"] = alert_id
    task_by_key["n_alert"]["sql_task"]["warehouse_id"] = warehouse_id

    for task in rendered["tasks"]:
        for dependency in task.get("depends_on", []):
            if dependency.get("task_key") not in task_by_key:
                raise ValueError(f"Task {task['task_key']} has unknown dependency {dependency.get('task_key')}")

    if rendered.get("max_concurrent_runs") != 1:
        raise ValueError("NovaCart job must preserve max_concurrent_runs=1")
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=Path("novacart_job.json"))
    parser.add_argument("--output", type=Path, default=Path("novacart_job.rendered.json"))
    parser.add_argument("--workspace-root", required=True, help="Absolute Databricks workspace folder")
    parser.add_argument("--dashboard-id", required=True)
    parser.add_argument("--alert-id", required=True)
    parser.add_argument("--warehouse-id", required=True)
    args = parser.parse_args()

    template = json.loads(args.template.read_text(encoding="utf-8"))
    rendered = render_job(
        template,
        args.workspace_root,
        args.dashboard_id,
        args.alert_id,
        args.warehouse_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8")
    print(f"Rendered Databricks job definition: {args.output}")


if __name__ == "__main__":
    main()
