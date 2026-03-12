"""
AutoMOOSE Plugin — Solidification (STUB)
=========================================
Phase-field solidification / dendritic growth.
Executable: phase_field-opt
Status: stub — input generator not yet implemented.
"""

PLUGIN = {
    "label":          "Solidification",
    "icon":           "❄️",
    "description":    "Phase-field solidification and dendritic growth (coming soon)",
    "executable_key": "MOOSE_EXEC",
    "status":         "stub",
    "params":         {},
    "presets":        {},
    "sweepable":      [],
    "result_keys":    [],
    "system_prompt":  "You are a MOOSE phase-field solidification expert.",
}


def generate_input(**kwargs) -> str:
    raise NotImplementedError("Solidification plugin not yet implemented.")


def parse_results(csv_data: dict) -> dict:
    return {}
