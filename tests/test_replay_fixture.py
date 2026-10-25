"""Tests for generating the local replay from the canonical mock pipeline."""

import json

from scripts.generate_replay_fixture import generate_fixture


def test_generator_writes_full_vendor_b_pending_approval_run(tmp_path) -> None:
    output = tmp_path / "replay" / "run.json"

    returned_path = generate_fixture(output)

    assert returned_path == output
    run = json.loads(output.read_text(encoding="utf-8"))
    assert run["selected_vendor_id"] == "vendor-b"
    assert run["status"] == "PENDING_APPROVAL"
    assert run["draft_po"]["quantity"] == 5000
    assert run["draft_po"]["unit_price"] == 27
    assert run["draft_po"]["total_price"] == 135000
    assert run["draft_po"]["terms"] == "Air Freight"
    assert len(run["vendor_comparison"]) >= 2
    assert len(run["stages"]) >= 6
