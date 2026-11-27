"""
Plugin Caller — demonstrates plugin.call capability to invoke other plugins.
"""

PLUGIN = {
    "name": "plugin_caller",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "description": "Demonstrates calling other plugins via plugin.call capability. Trigger with 'call plugin' or 'invoke plugin'.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {
                "type": "STRING",
                "description": "Name of the plugin to call (e.g., 'safe_calc', 'system_info')",
            },
            "params": {
                "type": "STRING",
                "description": "JSON string of parameters to pass to the target plugin",
            },
        },
        "required": ["target"],
    },
    "capabilities": ["plugin.call"],
    "sandboxed": False,
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Call another plugin."""
    import json

    target = parameters.get("target", "")
    params_str = parameters.get("params", "{}")

    try:
        params = json.loads(params_str) if params_str else {}
    except json.JSONDecodeError as e:
        return f"Invalid JSON in params: {e}"

    # Access the registry through player (if available)
    if player and hasattr(player, 'plugin_registry'):
        registry = player.plugin_registry
        result = registry.call_plugin("plugin_caller", target, params, player, session_memory)
        return f"Called '{target}': {result}"
    else:
        return "Plugin registry not accessible - cannot call other plugins"