"""
Lifecycle Demo Plugin — demonstrates on_load, on_enable, on_disable, on_unload, on_reload hooks.
"""

PLUGIN = {
    "name": "lifecycle_demo",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "description": "Demonstrates plugin lifecycle hooks. Trigger with 'lifecycle demo' or 'test lifecycle'.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "capabilities": ["ui.notify"],
    "sandboxed": False,
}

# Lifecycle hooks - these are called by the plugin loader
def on_load():
    """Called when plugin is first loaded at startup."""
    print("[SYS] [PluginLoader] lifecycle_demo: on_load hook called")
    # Could initialize connections, load config, etc.

def on_enable():
    """Called when plugin is enabled by user."""
    print("[SYS] [PluginLoader] lifecycle_demo: on_enable hook called")
    # Could start background tasks, open connections, etc.

def on_disable():
    """Called when plugin is disabled by user."""
    print("[SYS] [PluginLoader] lifecycle_demo: on_disable hook called")
    # Could stop background tasks, close connections, etc.

def on_unload():
    """Called when plugin file is deleted or app shuts down."""
    print("[SYS] [PluginLoader] lifecycle_demo: on_unload hook called")
    # Cleanup resources

def on_reload():
    """Called when plugin is hot-reloaded."""
    print("[SYS] [PluginLoader] lifecycle_demo: on_reload hook called")
    # Reinitialize without losing state

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Return lifecycle status."""
    return "Lifecycle demo plugin - hooks demonstrate on_load, on_enable, on_disable, on_unload, on_reload"