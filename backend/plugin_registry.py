"""
AutoMOOSE — Plugin Registry
============================
Discovers plugins from the plugins/ directory.
Each plugin must have a plugin.py with a PLUGIN dict and generate_input().
"""
import os
import importlib.util
from pathlib import Path

PLUGINS_DIR = Path(__file__).parent.parent / "plugins"
_registry: dict = {}


def _load_plugin(plugin_dir: Path) -> dict | None:
    plugin_file = plugin_dir / "plugin.py"
    if not plugin_file.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"plugins.{plugin_dir.name}.plugin", plugin_file)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "PLUGIN"):
        return None
    plugin = mod.PLUGIN.copy()
    plugin["_module"] = mod
    plugin["id"]      = plugin_dir.name
    return plugin


def load_all() -> dict:
    global _registry
    _registry = {}
    for d in sorted(PLUGINS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            p = _load_plugin(d)
            if p:
                _registry[p["id"]] = p
    return _registry


def get(plugin_id: str) -> dict | None:
    if not _registry:
        load_all()
    return _registry.get(plugin_id)


def all_plugins() -> dict:
    if not _registry:
        load_all()
    return _registry


def generate_input(plugin_id: str, params: dict) -> str:
    p = get(plugin_id)
    if not p:
        raise ValueError(f"Unknown plugin: {plugin_id}")
    return p["_module"].generate_input(**params)


def parse_results(plugin_id: str, csv_data: dict) -> dict:
    p = get(plugin_id)
    if not p:
        return {}
    fn = getattr(p["_module"], "parse_results", None)
    return fn(csv_data) if fn else {}


def get_system_prompt(plugin_id: str) -> str:
    p = get(plugin_id)
    if not p:
        return "You are a MOOSE simulation expert."
    return p.get("system_prompt", "You are a MOOSE simulation expert.")


def get_executable_key(plugin_id: str) -> str:
    """Returns the env var name that holds the executable path for this plugin."""
    p = get(plugin_id)
    if not p:
        return "MOOSE_EXEC"
    return p.get("executable_key", "MOOSE_EXEC")
