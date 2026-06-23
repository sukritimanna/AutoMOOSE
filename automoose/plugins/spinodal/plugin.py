"""
AutoMOOSE Plugin — Spinodal Decomposition (STUB)
=================================================
Cahn-Hilliard phase separation.
Executable: phase_field-opt
Status: stub — input generator not yet implemented.
"""

PLUGIN = {
    "label":          "Spinodal",
    "icon":           "🌊",
    "description":    "Cahn-Hilliard spinodal decomposition (coming soon)",
    "executable_key": "MOOSE_EXEC",
    "status":         "stub",
    "params":         {},
    "presets":        {},
    "sweepable":      [],
    "result_keys":    [],
    "system_prompt":  "You are a MOOSE Cahn-Hilliard spinodal decomposition expert.",
}


def generate_input(**kwargs) -> str:
    raise NotImplementedError("Spinodal plugin not yet implemented.")


def parse_results(csv_data: dict) -> dict:
    return {}
