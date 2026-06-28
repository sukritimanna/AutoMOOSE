"""Run-record serialization.

A run record is the JSON provenance artifact written for every run. This
assembles a record from a real plugin's parameter defaults plus representative
screening/falsification fields and checks that it serializes to JSON and
round-trips losslessly -- the property reproducibility depends on.
"""
import json

import automoose.plugin_registry as registry


def _example_record():
    plugin = registry.get("grain_growth")
    return {
        "run_id": "grain_growth_test",
        "physics": "grain_growth",
        "backend": "local",
        "provider": "anthropic",
        "model": "claude-sonnet",
        "params": plugin["params"],          # real plugin defaults
        "input_status": "input_ready",
        "run_status": "done",
        "wall_time_s": 42.5,
        "review_metrics": {"completed": True, "n_grains_final": 7},
        "credibility": "credible",
        "falsification_reason": None,
        "skeptic_diagnosis": {"T1_monotonicity": "pass", "T3_parabolic": "pass"},
    }


def test_run_record_round_trips_through_json():
    record = _example_record()
    restored = json.loads(json.dumps(record))
    assert restored == record


def test_run_record_params_survive_serialization():
    record = _example_record()
    restored = json.loads(json.dumps(record))
    assert restored["params"] == registry.get("grain_growth")["params"]
