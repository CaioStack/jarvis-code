"""
Drop-in JARVIS plugin template.

Copy this file, rename it (no leading underscore), fill in PLUGIN and run().
No other file needs to change — JARVIS discovers this automatically at startup.

ONE RULE IF YOUR PLUGIN NEEDS TO ASK A MODEL SOMETHING
    Go through `core.gemini`. Never build your own `genai.Client`.

        from core import gemini
        answer = gemini.text(prompt, tier=gemini.FAST)          # short decisions
        answer = gemini.text(prompt, tier=gemini.SMART,         # reasoning, code
                             timeout_ms=60_000)
        data   = gemini.as_json(prompt, tier=gemini.SMART)      # structured reply
        resp   = gemini.call(contents, tier=gemini.SMART)       # the full object

    You get three things that are impossible to add afterwards: a deadline on
    every call, a ladder that steps to another model when one is out of quota or
    not answering, and — since Mark LVI — whatever provider the user configured
    in ⚙ → ENGINE & PROVIDERS, so your plugin keeps working on Ollama or another
    API when Gemini's text quota is gone.

    A hardcoded client gets none of that and hangs forever when its one model is
    unwell, which is the exact fault the ladder was built to end.
"""

PLUGIN = {
    "name": "my_plugin",                     # snake_case, unique, ^[a-zA-Z_][a-zA-Z0-9_]{0,63}$
    "version": "1.0.0",                      # semantic version
    "author": "Your Name",                   # plugin author
    "license": "MIT",                        # SPDX license identifier
    "homepage": "https://example.com",       # plugin homepage/docs
    "repository": "https://github.com/user/repo",  # source code
    "keywords": ["example", "demo"],         # for discovery
    "dependencies": [],                      # pip packages needed (installed by user)
    "min_jarvis_version": "1.2.0",           # minimum Jarvis version required
    "description": (
        "One or two sentences Gemini uses to decide when to call this tool. "
        "Be explicit about trigger phrases and, if it could be confused with "
        "another tool, say which tool NOT to use instead (see game_updater's "
        "description in main.py for the pattern)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "example_arg": {"type": "STRING", "description": "What this argument means"},
        },
        "required": [],   # omit or leave empty for a zero-argument tool
    },
    # Phase 2: Capabilities — declare what permissions this plugin needs.
    # User must grant each capability in the Plugin Manager before the plugin can run.
    # Available capabilities:
    #   filesystem.read, filesystem.write, filesystem.delete, filesystem.list
    #   network.http, network.websocket, network.raw
    #   shell.exec, process.spawn, process.signal
    #   ui.notify, ui.input, input.keyboard, input.mouse
    #   audio.record, audio.play, video.record
    #   memory.read, memory.write, config.read, config.write
    #   plugin.call, plugin.discover
    "capabilities": [
        # "filesystem.read",
        # "network.http",
    ],
    # Phase 2: Sandbox — run plugin in isolated subprocess with resource limits.
    # When sandboxed=True, the plugin executes in a separate process with timeout
    # and memory limits. Requires all capabilities to be granted.
    "sandboxed": False,
    "sandbox_timeout": 30,      # seconds
    "sandbox_memory_mb": 256,   # memory limit (Linux only, requires cgroups)

    # Phase 2: Resource quotas — enforce limits at runtime (requires psutil)
    "cpu_quota_percent": 0.0,    # 0 = unlimited, e.g. 50.0 for 50%
    "memory_quota_mb": 0,        # 0 = unlimited, e.g. 200 for 200MB
    "disk_quota_mb": 0,          # 0 = unlimited

    # Phase 2: Audit logging — log all executions for compliance
    "audit_log": False,

    # Phase 2: Rate limiting — max calls per minute (0 = unlimited)
    "rate_limit": 0,

    # Phase 2: Debug mode — enable verbose logging for this plugin
    "debug": False,

    # Phase 2: Circuit breaker — prevent cascade failures
    "circuit_breaker_threshold": 5,  # failures before opening
    "circuit_breaker_timeout": 60,   # seconds before half-open

    # Phase 2: Retry policy — automatic retries with exponential backoff
    "max_retries": 0,
    "retry_delay": 1.0,       # initial delay in seconds
    "retry_backoff": 2.0,     # multiplier per retry

    # Phase 2: Plugin signing — will be set by registry.sign_plugin_*()
    "signature": "",
    "signer": "",
    "verified": False,

    # Phase 2: Categorization and favorites
    "category": "utility",     # utility, media, system, ai, network, etc.
    "tags": [],                # user-defined tags
    "favorite": False,         # user marked as favorite

    # Phase 2: Priority/ordering — higher runs first
    "priority": 0,
}

# Phase 2: Optional settings schema for UI configuration
# PLUGIN_SETTINGS = {
#     "namespace": "my_plugin",       # Config key (defaults to name)
#     "title": "My Plugin Config",    # UI title
#     "fields": [
#         {
#             "key": "api_key",
#             "label": "API Key",
#             "type": "secret",       # string, integer, number, boolean, choice
#             "default": "",
#             "required": True,
#         },
#         {
#             "key": "mode",
#             "label": "Operating Mode",
#             "type": "choice",
#             "choices": ["fast", "accurate"],
#             "default": "fast",
#         },
#         {
#             "key": "enabled",
#             "label": "Enable Feature X",
#             "type": "boolean",
#             "default": True,
#         },
#         {
#             "key": "threshold",
#             "label": "Threshold",
#             "type": "integer",
#             "default": 100,
#             "min": 0,
#             "max": 1000,
#         },
#     ],
#     "action": {                     # Optional test button
#         "label": "Test Connection",
#         "method": "test_connection",  # Function name in this module
#     },
# }

# Phase 2: Optional translations for i18n
# TRANSLATIONS = {
#     "en": {"description": "English description", "help": "English help text"},
#     "pt": {"description": "Descrição em português", "help": "Ajuda em português"},
#     "es": {"description": "Descripción en español", "help": "Ayuda en español"},
# }

# Phase 2: Optional changelog for version tracking
# CHANGELOG = [
#     {"version": "1.0.0", "date": "2024-01-15", "changes": "Initial release"},
#     {"version": "1.1.0", "date": "2024-02-20", "changes": "Added new feature X"},
# ]

# Phase 2: Optional migration functions for config version upgrades
# def migrate_v1_to_v2(config):
#     config.setdefault("new_field", "default_value")
#     return config


def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    parameters: dict of the args Gemini extracted, matching PLUGIN['parameters'].
    player: the JarvisUI instance — use player.write_log(f"JARVIS: ...") to log,
            same as actions/*.py. May be None.
    session_memory: reserved, usually None today (core tools mostly pass None too).
    Return a short natural-language string — this is spoken back to the user.
    Never raise: catch your own errors and return a spoken error string instead
    (the loader also catches exceptions as a second safety net, but don't rely on it).
    """
    example_arg = parameters.get("example_arg", "")
    try:
        result_text = f"Did the thing with {example_arg}."
    except Exception as e:
        return f"Sir, my_plugin failed: {e}"
    if player:
        try:
            player.write_log(f"JARVIS: {result_text}")
        except Exception:
            pass
    return result_text

# Phase 2: Optional lifecycle hooks
# def on_load():
#     """Called when plugin is first loaded at startup."""
#     print("[SYS] [PluginLoader] my_plugin: on_load hook called")

# def on_enable():
#     """Called when plugin is enabled by user."""
#     print("[SYS] [PluginLoader] my_plugin: on_enable hook called")

# def on_disable():
#     """Called when plugin is disabled by user."""
#     print("[SYS] [PluginLoader] my_plugin: on_disable hook called")

# def on_unload():
#     """Called when plugin file is deleted or app shuts down."""
#     print("[SYS] [PluginLoader] my_plugin: on_unload hook called")

# def on_reload():
#     """Called when plugin is hot-reloaded."""
#     print("[SYS] [PluginLoader] my_plugin: on_reload hook called")

# Phase 2: Optional test function for settings UI action button
# def test_connection():
#     """Test plugin configuration (called from UI action button)."""
#     return "Connection test successful!"