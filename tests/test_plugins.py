"""Plugin layer: discovery, schema contract, stub enforcement, serializability.

These mirror the plugin-extension boundary described in the Software Impacts
article: a plugin is a directory under ``automoose/plugins/`` whose
``plugin.py`` exposes a ``PLUGIN`` metadata dictionary and a
``generate_input(**params)`` function, auto-discovered by
``plugin_registry`` with no registration call.
"""
import json

import pytest

import automoose.plugin_registry as registry

# Keys every plugin (ready or stub) is expected to declare.
REQUIRED_KEYS = {"label", "status", "params", "executable_key", "sweepable"}
READY_PLUGINS = ("grain_growth", "spinodal")
STUB_PLUGINS = ("solidification", "ferro")


def test_discovery_finds_known_plugins():
    plugins = registry.load_all()
    assert set(READY_PLUGINS) | set(STUB_PLUGINS) <= set(plugins.keys())


def test_get_unknown_plugin_returns_none():
    assert registry.get("nonexistent_physics") is None


def test_plugin_schema_has_required_keys():
    for pid, plugin in registry.all_plugins().items():
        missing = REQUIRED_KEYS - set(plugin.keys())
        assert not missing, f"{pid} missing keys: {missing}"
        assert plugin["status"] in {"ready", "stub"}, pid
        assert isinstance(plugin["params"], dict), pid
        assert isinstance(plugin["sweepable"], (list, tuple)), pid


def test_ready_plugins_generate_input_string():
    for pid in READY_PLUGINS:
        plugin = registry.get(pid)
        assert plugin["status"] == "ready"
        deck = plugin["_module"].generate_input(**plugin["params"])
        assert isinstance(deck, str) and deck.strip(), f"{pid} produced empty input"


def test_stub_plugins_raise_not_implemented():
    for pid in STUB_PLUGINS:
        plugin = registry.get(pid)
        assert plugin["status"] == "stub"
        with pytest.raises(NotImplementedError):
            plugin["_module"].generate_input()


def test_plugin_metadata_is_json_serializable():
    # The plugin metadata (minus the live module object) is what flows into a
    # run record as provenance, so it must serialize cleanly.
    for pid, plugin in registry.all_plugins().items():
        meta = {k: v for k, v in plugin.items() if k != "_module"}
        json.dumps(meta)  # raises TypeError if any value is not serializable
