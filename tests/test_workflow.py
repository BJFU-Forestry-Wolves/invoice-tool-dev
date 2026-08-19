from pathlib import Path

import pytest

from order_date.workflow import WorkflowOptions, run_order_date_workflow


def test_workflow_rejects_output_inside_repository(tmp_path: Path):
    options = WorkflowOptions(
        csv_path=tmp_path / "input.csv",
        attach_root=tmp_path / "attachments",
        output_dir=Path(__file__).parents[1] / "private-output",
    )

    with pytest.raises(ValueError, match="Git 仓库外"):
        run_order_date_workflow(options)
