"""Generate a deterministic, offline replay run from the real mock pipeline."""

from __future__ import annotations

import argparse
from importlib.resources import files
from pathlib import Path

from chainmind.core.config import Settings
from chainmind.core.events import EventStore
from chainmind.core.models import DisruptionEvent
from chainmind.factory import create_pipeline

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dashboard" / "public" / "replay-run.json"


def generate_fixture(output: Path = DEFAULT_OUTPUT) -> Path:
    """Run the seeded scenario through mock agents and persist the result as JSON."""

    seed = files("chainmind.data").joinpath("sample_disruption.json").read_text(encoding="utf-8")
    event = DisruptionEvent.model_validate_json(seed)
    run = create_pipeline(Settings(mode="mock"), EventStore()).run(event)
    if run.draft_po is None or run.selected_vendor_id != "vendor-b":
        raise RuntimeError("The canonical mock scenario did not produce its expected draft PO.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    path = generate_fixture(arguments.output)
    print(f"Generated mock replay fixture: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
