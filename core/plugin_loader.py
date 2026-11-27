"""
Plugin discovery, validation, collision detection, and dispatch.

Discovery runs once (JarvisLive.__init__ calls discover_plugins()); the resulting
PluginRegistry is cached for the process lifetime. Enable/disable state is re-read
from config on every call to get_tool_declarations() / run() / list_for_ui(), so
toggling a plugin does not require restarting the app or re-importing anything.

Phase 2 additions:
- Hot-reload via filesystem watchdog (watchdog library optional)
- Capability-based permission system (filesystem, network, shell, etc.)
- Sandbox execution for untrusted plugins (subprocess isolation)
- Plugin state preservation across reloads
- Enhanced manifest schema with versioning, author, dependencies
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from memory.config_manager import get_plugin_enabled, get_plugin_config

# Hot-reload: watchdog is optional; if absent, hot-reload is silently disabled
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    _WATCHDOG_AVAILABLE = True
except Exception:
    _WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {"type": "OBJECT", "properties": {}}

# Optional, and the same contract actions use: a plugin that takes a moment can
# say so, and the model carries on talking instead of waiting on it. See
# core/action_loader.py for what each value means.
_BEHAVIORS = ("BLOCKING", "NON_BLOCKING")
_SCHEDULING = ("WHEN_IDLE", "SILENT", "INTERRUPT")

# ── Capability-based permission system ────────────────────────────────────────
# Each capability is a coarse-grained permission. Plugins declare what they need
# in PLUGIN["capabilities"] = ["filesystem.read", "network.http", ...].
# The user approves/denies each capability per plugin via the UI.
# Capabilities are enforced at plugin RUN time, not import time.
_VALID_CAPABILITIES = (
    # Filesystem
    "filesystem.read",      # Read files in allowed paths
    "filesystem.write",     # Write files in allowed paths
    "filesystem.delete",    # Delete files
    "filesystem.list",      # List directories
    # Network
    "network.http",         # HTTP/HTTPS requests (outbound)
    "network.websocket",    # WebSocket connections
    "network.raw",          # Raw sockets (TCP/UDP)
    # System
    "shell.exec",           # Execute shell commands
    "process.spawn",        # Spawn subprocesses
    "process.signal",       # Send signals to processes
    # UI/Input
    "ui.notify",            # Send notifications to user
    "ui.input",             # Request input from user
    "input.keyboard",       # Simulate keyboard input
    "input.mouse",          # Simulate mouse input
    # Audio/Video
    "audio.record",         # Record from microphone
    "audio.play",           # Play audio
    "video.record",         # Record screen/camera
    # Data
    "memory.read",          # Read long-term memory
    "memory.write",         # Write to long-term memory
    "config.read",          # Read configuration
    "config.write",         # Write configuration
    # Plugin-to-plugin
    "plugin.call",          # Call other plugins
    "plugin.discover",      # List available plugins
)

# Capability groups for UI convenience
_CAPABILITY_GROUPS = {
    "Filesystem": [c for c in _VALID_CAPABILITIES if c.startswith("filesystem")],
    "Network":    [c for c in _VALID_CAPABILITIES if c.startswith("network")],
    "System":     [c for c in _VALID_CAPABILITIES if c.startswith(("shell", "process"))],
    "UI/Input":   [c for c in _VALID_CAPABILITIES if c.startswith(("ui", "input"))],
    "Media":      [c for c in _VALID_CAPABILITIES if c.startswith(("audio", "video"))],
    "Data":       [c for c in _VALID_CAPABILITIES if c.startswith(("memory", "config"))],
    "Plugins":    [c for c in _VALID_CAPABILITIES if c.startswith("plugin")],
}


def _opt_upper(value, allowed: tuple[str, ...]) -> Optional[str]:
    v = str(value or "").strip().upper()
    return v if v in allowed else None

def _opt_tier(value) -> Optional[str]:
    """"core" or "extra" from a declaration, or None when it did not say.

    Anything else is treated as "did not say" rather than as an error: a typo
    should fall back to the default ranking, not stop a working tool loading.
    """
    text = str(value or "").strip().lower()
    return text if text in ("core", "extra") else None


def _opt_text(value) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


@dataclass
class PluginRecord:
    name: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(_DEFAULT_PARAMS))
    run: Optional[Callable] = None
    file: str = ""
    valid: bool = False
    error: str = ""
    settings: Optional[dict] = None   # optional PLUGIN_SETTINGS schema (config fields)
    behavior: Optional[str] = None    # None = the API's default (blocking)
    scheduling: Optional[str] = None  # None = the API's default (WHEN_IDLE)
    # Read by providers/schema.py when a small model gets a tool budget; never
    # sent to any API — main.py strips both before the Gemini config is built.
    #   tier   "core" | "extra" — this file's own opinion of whether it should
    #          survive a tight budget, instead of that being decided by the
    #          order files happen to be discovered in.
    #   brief  a short description used in place of the long one when a budget
    #          is in force. Nothing is deleted: Gemini still gets the full text.
    tier: Optional[str] = None
    brief: Optional[str] = None

    # Phase 2: Enhanced manifest fields
    version: str = "1.0.0"
    author: str = ""
    license: str = "MIT"
    homepage: str = ""
    repository: str = ""
    keywords: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # pip packages
    min_jarvis_version: str = "1.0.0"

    # Phase 2: Permission system
    capabilities: list[str] = field(default_factory=list)  # declared capabilities
    granted_capabilities: list[str] = field(default_factory=list)  # user-approved

    # Phase 2: Sandbox configuration
    sandboxed: bool = False  # run in isolated subprocess
    sandbox_timeout: int = 30  # seconds
    sandbox_memory_mb: int = 256  # memory limit

    # Phase 2: Hot-reload state preservation
    _state: dict = field(default_factory=dict, repr=False)  # preserved across reloads
    _last_modified: float = 0  # for change detection
    _reload_count: int = 0

    # Phase 2: Performance metrics
    _run_count: int = 0
    _total_run_time: float = 0.0
    _last_run_time: float = 0.0
    _last_error: str = ""
    _last_run: float = 0  # timestamp

    # Phase 2: Debug mode
    debug: bool = False  # enable debug logging for this plugin

    # Phase 2: Analytics/usage tracking
    _success_count: int = 0
    _failure_count: int = 0
    _first_run: float = 0
    _last_success: float = 0
    _last_failure: float = 0


class PluginRegistry:
    def __init__(self, plugins: dict[str, PluginRecord], logger: Callable[[str], None],
                 notify: Callable[[str], None] | None = None):
        self._plugins = plugins          # name -> PluginRecord, VALID entries only
        self._all_records: list[PluginRecord] = []   # valid + invalid, for UI listing
        self._logger = logger
        # Where user-facing notices go. `logger` is the console transcript and
        # carries everything; `notify` reaches the activity log, so only things
        # the user has to know about are sent to it. Defaults to dropping them,
        # which keeps every existing single-sink caller working unchanged.
        self._notify = notify or (lambda _msg: None)

    # -- called by main.py at LiveConnectConfig build time --
    def get_tool_declarations(self) -> list[dict]:
        decls = []
        for name, rec in self._plugins.items():
            if get_plugin_enabled(name):
                decl = {
                    "name": rec.name,
                    "description": rec.description,
                    "parameters": rec.parameters,
                }
                if rec.behavior:
                    decl["behavior"] = rec.behavior
                # Budget metadata. NOT part of any API's schema — main.py calls
                # providers.schema.strip_meta() before the Gemini config is
                # built, and budget() consumes them on the local-engine path.
                if rec.tier:
                    decl["tier"] = rec.tier
                if rec.brief:
                    decl["brief"] = rec.brief
                decls.append(decl)
        return decls

    def has(self, name: str) -> bool:
        return name in self._plugins

    def scheduling(self, name: str) -> Optional[str]:
        """How this plugin's result should re-enter the conversation, if it said."""
        rec = self._plugins.get(name)
        return rec.scheduling if rec else None

    # -- called by main.py from _execute_tool's else branch --
    def run(self, name: str, parameters: dict, player=None, session_memory=None) -> str:
        rec = self._plugins.get(name)
        if rec is None or not rec.valid:
            return f"Plugin '{name}' is not available."
        if not get_plugin_enabled(name):
            return f"The '{name}' plugin is currently disabled."

        # Phase 2: Capability check
        missing_caps = [c for c in rec.capabilities if c not in rec.granted_capabilities]
        if missing_caps:
            self._logger(f"[SYS] [PluginLoader] Plugin '{name}' missing capabilities: {missing_caps}")
            return (f"Plugin '{name}' requires ungranted capabilities: {', '.join(missing_caps)}. "
                    f"Grant them in the Plugin Manager to use this plugin.")

        # Phase 2: Debug logging
        if rec.debug:
            self._logger(f"[SYS] [PluginLoader] DEBUG: Running '{name}' with params: {parameters}")

        # Phase 2: Performance tracking
        import time
        start_time = time.perf_counter()
        now = time.time()
        rec._last_run = now

        # Track first run
        if rec._first_run == 0:
            rec._first_run = now

        try:
            if rec.sandboxed:
                result = self._run_sandboxed(rec, parameters, player, session_memory)
            else:
                result = _call_run(rec.run, parameters, player, session_memory) or "Done."

            # Track successful run
            elapsed = time.perf_counter() - start_time
            rec._run_count += 1
            rec._total_run_time += elapsed
            rec._last_run_time = elapsed
            rec._last_error = ""
            rec._success_count += 1
            rec._last_success = now

            # Phase 2: Debug logging for result
            if rec.debug:
                self._logger(f"[SYS] [PluginLoader] DEBUG: '{name}' completed in {elapsed*1000:.2f}ms: {result[:100]}")
            return result

        except Exception as e:
            # Track failed run
            elapsed = time.perf_counter() - start_time
            rec._run_count += 1
            rec._total_run_time += elapsed
            rec._last_run_time = elapsed
            rec._last_error = str(e)
            rec._failure_count += 1
            rec._last_failure = now
            self._logger(f"[SYS] [PluginLoader] Plugin '{name}' crashed during run(): {e}")
            self._notify(f"Plugin '{name}' failed — see the console for details.")
            traceback.print_exc()
            return f"Sir, the '{name}' plugin failed: {e}"

    def _run_sandboxed(self, rec: PluginRecord, parameters: dict, player, session_memory) -> str:
        """Execute plugin in isolated subprocess with resource limits."""
        import subprocess
        import tempfile
        import os

        # Prepare plugin code for subprocess execution
        plugin_code = f'''
import sys, json, traceback
sys.path.insert(0, {json.dumps(str(Path(__file__).resolve().parent.parent))})

from plugins.{rec.name} import run as plugin_run

if __name__ == "__main__":
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {{}}
    try:
        result = plugin_run(params)
        print(json.dumps({{"ok": True, "result": str(result)}}))
    except Exception as e:
        print(json.dumps({{"ok": False, "error": str(e), "traceback": traceback.format_exc()}}))
        sys.exit(1)
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            script_path = f.name

        try:
            # Run with resource limits (Linux)
            cmd = [sys.executable, script_path, json.dumps(parameters)]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=rec.sandbox_timeout,
                # Note: memory limit requires cgroups or resource module on Linux
            )
            if proc.returncode != 0:
                try:
                    result = json.loads(proc.stdout.strip())
                    return f"Sandboxed plugin failed: {result.get('error', 'Unknown error')}"
                except Exception:
                    return f"Sandboxed plugin failed (exit {proc.returncode}): {proc.stderr[:200]}"

            result = json.loads(proc.stdout.strip())
            return result.get("result", "Done.")

        except subprocess.TimeoutExpired:
            return f"Plugin '{rec.name}' timed out after {rec.sandbox_timeout}s (sandbox limit)."
        except Exception as e:
            return f"Sandbox execution error: {e}"
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass

    # -- called by ui.py's settings tab to render per-plugin config forms --
    def settings_schemas(self) -> list[dict]:
        """One entry per settings SECTION, for enabled plugins that declare a
        PLUGIN_SETTINGS schema. Sections are deduped by namespace so a suite of
        plugins sharing one namespace (e.g. the printer trio) shows a single
        form. Current stored values are merged in so the UI can pre-fill fields.
        """
        seen: set[str] = set()
        out: list[dict] = []
        for name, rec in self._plugins.items():
            if not rec.settings or not get_plugin_enabled(name):
                continue
            ns = rec.settings.get("namespace") or rec.name
            if ns in seen:
                continue
            seen.add(ns)
            out.append({
                "plugin":    rec.name,
                "namespace": ns,
                "title":     rec.settings.get("title") or rec.name,
                "fields":    rec.settings.get("fields", []),
                "values":    get_plugin_config(ns),
                "action":    rec.settings.get("action"),   # optional test/connect button
            })
        return out

    # -- called by ui.py's Plugin Manager overlay --
    def list_for_ui(self) -> list[dict]:
        out = []
        for rec in self._all_records:
            # Check dependencies for this plugin
            deps_installed = True
            missing_deps = []
            if rec.valid and rec.dependencies:
                deps_installed, missing_deps = self.check_dependencies(rec.name)

            out.append({
                "name": rec.name,
                "description": rec.description,
                "file": rec.file,
                "valid": rec.valid,
                "error": rec.error,
                "enabled": get_plugin_enabled(rec.name) if rec.valid else False,
                # Phase 2: Enhanced metadata for UI
                "version": rec.version,
                "author": rec.author,
                "license": rec.license,
                "homepage": rec.homepage,
                "repository": rec.repository,
                "keywords": rec.keywords,
                "dependencies": rec.dependencies,
                "dependencies_installed": deps_installed,
                "missing_dependencies": missing_deps,
                "min_jarvis_version": rec.min_jarvis_version,
                "capabilities": rec.capabilities,
                "granted_capabilities": rec.granted_capabilities,
                "capability_groups": _CAPABILITY_GROUPS,
                "sandboxed": rec.sandboxed,
                "sandbox_timeout": rec.sandbox_timeout,
                "sandbox_memory_mb": rec.sandbox_memory_mb,
                "reload_count": rec._reload_count,
            })
        return out

    # Phase 2: Dependency checking
    def check_dependencies(self, plugin_name: str) -> tuple[bool, list[str]]:
        """Check if a plugin's declared dependencies are installed.

        Returns (all_installed, missing_packages).
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return False, [f"Plugin '{plugin_name}' not found"]
        missing = []
        for dep in rec.dependencies:
            try:
                __import__(dep.replace('-', '_'))
            except ImportError:
                missing.append(dep)
        return len(missing) == 0, missing

    def check_all_dependencies(self) -> dict[str, list[str]]:
        """Check dependencies for all loaded plugins.

        Returns dict of plugin_name -> missing_packages (empty if all installed).
        """
        result = {}
        for name, rec in self._plugins.items():
            if rec.valid and rec.dependencies:
                _, missing = self.check_dependencies(name)
                if missing:
                    result[name] = missing
        return result

    # Phase 2: Performance metrics
    def get_performance(self, plugin_name: str) -> dict:
        """Get performance metrics for a plugin."""
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"error": f"Plugin '{plugin_name}' not found"}

        avg_time = rec._total_run_time / rec._run_count if rec._run_count > 0 else 0
        success_rate = (rec._success_count / rec._run_count * 100) if rec._run_count > 0 else 0

        return {
            "run_count": rec._run_count,
            "total_time": rec._total_run_time,
            "avg_time": avg_time,
            "last_run_time": rec._last_run_time,
            "last_error": rec._last_error,
            "last_run": rec._last_run,
            # Analytics
            "success_count": rec._success_count,
            "failure_count": rec._failure_count,
            "success_rate": success_rate,
            "first_run": rec._first_run,
            "last_success": rec._last_success,
            "last_failure": rec._last_failure,
        }

    def get_all_performance(self) -> dict[str, dict]:
        """Get performance metrics for all plugins."""
        return {name: self.get_performance(name) for name in self._plugins}

    # Phase 2: Version compatibility checking
    def check_version_compatibility(self, plugin_name: str, current_version: str = "1.2.0") -> dict:
        """Check if a plugin's min_jarvis_version is compatible with current version.

        Returns dict with: compatible, min_version, current_version, reason
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"compatible": False, "error": f"Plugin '{plugin_name}' not found"}

        min_version = rec.min_jarvis_version or "1.0.0"

        def parse_version(v: str) -> tuple:
            try:
                parts = v.split('.')
                return tuple(int(p) for p in parts[:3])
            except Exception:
                return (0, 0, 0)

        min_tuple = parse_version(min_version)
        current_tuple = parse_version(current_version)

        compatible = current_tuple >= min_tuple
        reason = ""
        if not compatible:
            reason = f"Requires Jarvis {min_version}, current is {current_version}"

        return {
            "compatible": compatible,
            "min_version": min_version,
            "current_version": current_version,
            "reason": reason,
        }

    def check_all_compatibility(self, current_version: str = "1.2.0") -> dict[str, dict]:
        """Check version compatibility for all plugins."""
        return {
            name: self.check_version_compatibility(name, current_version)
            for name in self._plugins
        }

    # Phase 2: Plugin health/status monitoring
    def get_plugin_health(self, plugin_name: str) -> dict:
        """Get health status for a plugin.

        Returns dict with: status, capabilities_ok, dependencies_ok, last_error, run_count, last_run
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"status": "not_found", "error": f"Plugin '{plugin_name}' not found"}

        if not rec.valid:
            return {"status": "invalid", "error": rec.error}

        # Check capabilities
        caps_ok = True
        missing_caps = [c for c in rec.capabilities if c not in rec.granted_capabilities]
        if missing_caps:
            caps_ok = False

        # Check dependencies
        deps_ok = True
        missing_deps = []
        if rec.dependencies:
            deps_ok, missing_deps = self.check_dependencies(plugin_name)

        # Determine overall status
        if not caps_ok or not deps_ok:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "capabilities_ok": caps_ok,
            "missing_capabilities": missing_caps,
            "dependencies_ok": deps_ok,
            "missing_dependencies": missing_deps,
            "version": rec.version,
            "sandboxed": rec.sandboxed,
            "reload_count": rec._reload_count,
            "last_modified": rec._last_modified,
        }

    def get_all_health(self) -> dict[str, dict]:
        """Get health status for all plugins."""
        return {name: self.get_plugin_health(name) for name in self._plugins}

    # Phase 2: Plugin-to-plugin communication
    def call_plugin(self, caller_name: str, target_name: str, parameters: dict,
                     player=None, session_memory=None) -> str:
        """Call another plugin (requires plugin.call capability).

        This allows plugins to invoke other plugins programmatically.
        """
        caller_rec = self._plugins.get(caller_name)
        if not caller_rec:
            return f"Caller plugin '{caller_name}' not found"

        # Check plugin.call capability
        if "plugin.call" not in caller_rec.granted_capabilities:
            return f"Plugin '{caller_name}' lacks 'plugin.call' capability"

        target_rec = self._plugins.get(target_name)
        if not target_rec or not target_rec.valid:
            return f"Target plugin '{target_name}' not available"

        if not get_plugin_enabled(target_name):
            return f"Target plugin '{target_name}' is disabled"

        # Execute the target plugin
        try:
            return _call_run(target_rec.run, parameters, player, session_memory) or "Done."
        except Exception as e:
            return f"Plugin '{target_name}' failed: {e}"

    def list_available_plugins(self) -> list[dict]:
        """List all available plugins for plugin.discover capability."""
        plugins = []
        for name, rec in self._plugins.items():
            if rec.valid and get_plugin_enabled(name):
                plugins.append({
                    "name": name,
                    "description": rec.description,
                    "parameters": rec.parameters,
                })
        return plugins

    # Phase 2: Plugin lifecycle hooks
    def _call_lifecycle_hook(self, rec: PluginRecord, hook_name: str) -> bool:
        """Call a lifecycle hook on a plugin if it exists.

        Returns True if hook was called, False if not defined or error.
        Hooks: on_load, on_unload, on_enable, on_disable, on_reload
        """
        if not rec.valid or not rec.run:
            return False

        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return False

        hook_fn = getattr(module, hook_name, None)
        if not callable(hook_fn):
            return False

        try:
            hook_fn()
            return True
        except Exception as e:
            self._logger(f"[SYS] [PluginLoader] Plugin '{rec.name}' {hook_name} hook failed: {e}")
            return False

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin and call on_enable hook."""
        from memory.config_manager import save_plugin_enabled
        rec = self._plugins.get(plugin_name)
        if not rec or not rec.valid:
            return False
        save_plugin_enabled(plugin_name, True)
        self._call_lifecycle_hook(rec, "on_enable")
        self._notify(f"Plugin '{plugin_name}' enabled")
        return True

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin and call on_disable hook."""
        from memory.config_manager import save_plugin_enabled
        rec = self._plugins.get(plugin_name)
        if not rec or not rec.valid:
            return False
        save_plugin_enabled(plugin_name, False)
        self._call_lifecycle_hook(rec, "on_disable")
        self._notify(f"Plugin '{plugin_name}' disabled")
        return True

    # Phase 2: Capability management
    def grant_capability(self, plugin_name: str, capability: str) -> bool:
        """Grant a capability to a plugin. Returns True if successful."""
        if capability not in _VALID_CAPABILITIES:
            return False
        rec = self._plugins.get(plugin_name)
        if rec and capability not in rec.granted_capabilities:
            rec.granted_capabilities.append(capability)
            self._save_capabilities()
            return True
        return False

    def revoke_capability(self, plugin_name: str, capability: str) -> bool:
        """Revoke a capability from a plugin. Returns True if successful."""
        rec = self._plugins.get(plugin_name)
        if rec and capability in rec.granted_capabilities:
            rec.granted_capabilities.remove(capability)
            self._save_capabilities()
            return True
        return False

    # Phase 2: Debug mode
    def enable_debug(self, plugin_name: str) -> bool:
        """Enable debug logging for a plugin."""
        rec = self._plugins.get(plugin_name)
        if rec:
            rec.debug = True
            self._logger(f"[SYS] [PluginLoader] Debug mode enabled for '{plugin_name}'")
            return True
        return False

    def disable_debug(self, plugin_name: str) -> bool:
        """Disable debug logging for a plugin."""
        rec = self._plugins.get(plugin_name)
        if rec:
            rec.debug = False
            self._logger(f"[SYS] [PluginLoader] Debug mode disabled for '{plugin_name}'")
            return True
        return False

    def _save_capabilities(self) -> None:
        """Persist granted capabilities to config."""
        from memory.config_manager import get_plugin_config, save_plugin_config
        for name, rec in self._plugins.items():
            if rec.granted_capabilities:
                cfg = get_plugin_config(name)
                cfg["granted_capabilities"] = rec.granted_capabilities
                save_plugin_config(name, cfg)

    def load_granted_capabilities(self) -> None:
        """Load granted capabilities from config."""
        from memory.config_manager import get_plugin_config
        for name, rec in self._plugins.items():
            cfg = get_plugin_config(name)
            granted = cfg.get("granted_capabilities", [])
            if isinstance(granted, list):
                rec.granted_capabilities = [c for c in granted if c in _VALID_CAPABILITIES]

    # Phase 2: Plugin export/import (configuration migration)
    def export_plugin_config(self, plugin_name: str) -> dict:
        """Export a plugin's configuration for backup/migration.

        Returns dict with: capabilities, granted_capabilities, debug, settings, metadata
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"error": f"Plugin '{plugin_name}' not found"}

        from memory.config_manager import get_plugin_config
        settings = get_plugin_config(plugin_name)

        return {
            "name": rec.name,
            "version": rec.version,
            "file": rec.file,
            "capabilities": rec.capabilities,
            "granted_capabilities": rec.granted_capabilities,
            "debug": rec.debug,
            "sandboxed": rec.sandboxed,
            "sandbox_timeout": rec.sandbox_timeout,
            "sandbox_memory_mb": rec.sandbox_memory_mb,
            "settings": settings,
            "exported_at": time.time(),
        }

    def export_all_configs(self) -> dict:
        """Export all plugin configurations."""
        return {
            "plugins": {name: self.export_plugin_config(name) for name in self._plugins},
            "version": "1.2.0",
        }

    def import_plugin_config(self, plugin_name: str, config: dict) -> bool:
        """Import a plugin's configuration from backup/migration."""
        rec = self._plugins.get(plugin_name)
        if not rec:
            return False

        # Restore capabilities
        if "granted_capabilities" in config:
            rec.granted_capabilities = [
                c for c in config["granted_capabilities"] if c in _VALID_CAPABILITIES
            ]

        # Restore debug mode
        if "debug" in config:
            rec.debug = bool(config["debug"])

        # Restore sandbox settings (if provided in config)
        if "sandboxed" in config:
            rec.sandboxed = bool(config["sandboxed"])
        if "sandbox_timeout" in config:
            rec.sandbox_timeout = int(config["sandbox_timeout"])
        if "sandbox_memory_mb" in config:
            rec.sandbox_memory_mb = int(config["sandbox_memory_mb"])

        # Save capabilities to config
        if "granted_capabilities" in config:
            from memory.config_manager import get_plugin_config, save_plugin_config
            cfg = get_plugin_config(plugin_name)
            cfg["granted_capabilities"] = rec.granted_capabilities
            save_plugin_config(plugin_name, cfg)

        # Restore settings
        if "settings" in config:
            from memory.config_manager import save_plugin_config
            for key, value in config["settings"].items():
                save_plugin_config(plugin_name, {key: value})

        self._logger(f"[SYS] [PluginLoader] Imported config for '{plugin_name}'")
        return True

    # Phase 2: Plugin security scanner
    def scan_plugin_security(self, plugin_name: str) -> dict:
        """Scan a plugin for potentially dangerous code patterns.

        Returns dict with: safe, issues (list of findings), risk_level
        """
        rec = self._plugins.get(plugin_name)
        if not rec or not rec.valid:
            return {"error": f"Plugin '{plugin_name}' not found or invalid"}

        import inspect
        import ast

        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return {"error": f"Plugin module not loaded"}

        source = inspect.getsource(module)

        # Dangerous patterns to check
        dangerous_patterns = [
            ("eval", "Use of eval() - can execute arbitrary code"),
            ("exec", "Use of exec() - can execute arbitrary code"),
            ("compile", "Use of compile() - can execute arbitrary code"),
            ("__import__", "Dynamic imports - can load arbitrary modules"),
            ("subprocess", "Subprocess execution - can run system commands"),
            ("os.system", "os.system() - can run shell commands"),
            ("os.popen", "os.popen() - can run shell commands"),
            ("ctypes", "ctypes - can call C libraries"),
            ("pickle", "pickle - can execute code on deserialization"),
            ("marshal", "marshal - can execute code on deserialization"),
            ("importlib", "importlib - dynamic module loading"),
            ("open", "File operations - check for path traversal"),
        ]

        issues = []
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id
                        for pattern, desc in dangerous_patterns:
                            if func_name == pattern:
                                issues.append({
                                    "type": "dangerous_call",
                                    "pattern": pattern,
                                    "description": desc,
                                    "line": node.lineno,
                                })
                    elif isinstance(node.func, ast.Attribute):
                        attr_name = node.func.attr
                        for pattern, desc in dangerous_patterns:
                            if attr_name == pattern:
                                issues.append({
                                    "type": "dangerous_call",
                                    "pattern": pattern,
                                    "description": desc,
                                    "line": node.lineno,
                                })
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        for pattern, desc in dangerous_patterns:
                            if pattern in alias.name:
                                issues.append({
                                    "type": "dangerous_import",
                                    "pattern": pattern,
                                    "description": f"Import of {alias.name}: {desc}",
                                    "line": node.lineno,
                                })
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        for pattern, desc in dangerous_patterns:
                            if pattern in node.module:
                                issues.append({
                                    "type": "dangerous_import",
                                    "pattern": pattern,
                                    "description": f"Import from {node.module}: {desc}",
                                    "line": node.lineno,
                                })
        except Exception as e:
            issues.append({
                "type": "parse_error",
                "pattern": "N/A",
                "description": f"Failed to parse source: {e}",
                "line": 0,
            })

        # Determine risk level
        if not issues:
            risk_level = "safe"
        elif any(i["type"] == "parse_error" for i in issues):
            risk_level = "unknown"
        elif any(i["pattern"] in ("eval", "exec", "compile", "subprocess", "os.system", "os.popen", "ctypes") for i in issues):
            risk_level = "high"
        elif any(i["pattern"] in ("__import__", "importlib", "pickle", "marshal") for i in issues):
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "safe": len(issues) == 0,
            "risk_level": risk_level,
            "issues": issues,
            "scanned_at": time.time(),
        }

    # Phase 2: Hot-reload via filesystem watchdog
    def start_hot_reload(self, plugins_dir: Path, core_tool_names: set[str]) -> bool:
        """Start watching the plugins directory for changes.

        Returns True if watchdog is available and watcher started.
        If watchdog is not installed, hot-reload is silently disabled.
        """
        if not _WATCHDOG_AVAILABLE:
            self._logger("[SYS] [PluginLoader] Hot-reload unavailable: watchdog not installed")
            return False

        if hasattr(self, '_observer') and self._observer is not None:
            self._logger("[SYS] [PluginLoader] Hot-reload already running")
            return True

        class PluginFileHandler(FileSystemEventHandler):
            def __init__(self, registry):
                self.registry = registry
                self._last_event = 0

            def on_modified(self, event):
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path.suffix != ".py" or path.name.startswith("_"):
                    return
                # Debounce: ignore events within 500ms of each other
                now = time.time()
                if now - self._last_event < 0.5:
                    return
                self._last_event = now
                self.registry._reload_plugin(path, core_tool_names)

            def on_created(self, event):
                self.on_modified(event)

            def on_deleted(self, event):
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if path.suffix != ".py" or path.name.startswith("_"):
                    return
                self.registry._unload_plugin(path.stem)

        self._observer = Observer()
        self._observer.schedule(PluginFileHandler(self), str(plugins_dir), recursive=False)
        self._observer.start()
        self._plugins_dir = plugins_dir
        self._core_tool_names = core_tool_names
        self._logger("[SYS] [PluginLoader] Hot-reload started")
        return True

    def stop_hot_reload(self) -> None:
        """Stop the filesystem watcher."""
        if hasattr(self, '_observer') and self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2.0)
            self._observer = None
            self._logger("[SYS] [PluginLoader] Hot-reload stopped")

    def _reload_plugin(self, path: Path, core_tool_names: set[str]) -> None:
        """Reload a single plugin file, preserving its state."""
        import importlib
        import sys

        module_name = f"plugins.{path.stem}"

        # Preserve state from old record if it exists
        old_rec = self._plugins.get(path.stem)
        old_state = old_rec._state if old_rec else {}
        old_granted = old_rec.granted_capabilities if old_rec else []
        old_reload_count = old_rec._reload_count if old_rec else 0
        old_last_modified = path.stat().st_mtime if path.exists() else 0

        try:
            # Remove old module from sys.modules
            if module_name in sys.modules:
                del sys.modules[module_name]

            # Import fresh
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError("could not build import spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Validate
            rec = _validate(module, path.name)

            if rec.valid and rec.name in core_tool_names:
                rec = PluginRecord(name=rec.name, file=path.name,
                                    error=f"Name '{rec.name}' collides with a core tool — rejected.")
            elif rec.valid and rec.name in self._plugins and rec.name != path.stem:
                other = self._plugins[rec.name].file
                rec = PluginRecord(name=rec.name, file=path.name,
                                    error=f"Name '{rec.name}' already used by plugin '{other}' — rejected.")

            if rec.valid:
                # Preserve state across reload
                rec._state = old_state
                rec.granted_capabilities = old_granted
                rec._reload_count = old_reload_count + 1
                rec._last_modified = old_last_modified

                self._plugins[rec.name] = rec
                self._logger(f"[SYS] [PluginLoader] Plugin reloaded: {rec.name} ({path.name}, reload #{rec._reload_count})")

                # Call on_reload hook
                self._call_lifecycle_hook(rec, "on_reload")
            else:
                self._logger(f"[SYS] [PluginLoader] Plugin reload failed: {path.name} — {rec.error}")
                # Remove from plugins if it was there before
                if path.stem in self._plugins:
                    del self._plugins[path.stem]

        except Exception as e:
            self._logger(f"[SYS] [PluginLoader] Plugin reload error: {path.name} — {e}")
            traceback.print_exc()
            # Remove from plugins if it was there before
            if path.stem in self._plugins:
                del self._plugins[path.stem]

    def _unload_plugin(self, name: str) -> None:
        """Unload a plugin when its file is deleted."""
        # Call on_unload hook before removing
        old_rec = self._plugins.get(name)
        if old_rec:
            self._call_lifecycle_hook(old_rec, "on_unload")

        if name in self._plugins:
            del self._plugins[name]
            self._logger(f"[SYS] [PluginLoader] Plugin unloaded: {name}")


def _call_run(run_fn, parameters, player, session_memory):
    """Invoke run() passing only the kwargs it actually declares (or all of them
    if it has **kwargs), so a minimal `def run(parameters):` plugin still works."""
    sig = inspect.signature(run_fn)
    has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    kwargs = {}
    if has_var_kw or "player" in sig.parameters:
        kwargs["player"] = player
    if has_var_kw or "session_memory" in sig.parameters:
        kwargs["session_memory"] = session_memory
    return run_fn(parameters, **kwargs)


def _validate(module, filename: str) -> PluginRecord:
    """Returns a PluginRecord; .valid=False + .error set on any problem. Never raises."""
    plugin_meta = getattr(module, "PLUGIN", None)
    if not isinstance(plugin_meta, dict):
        return PluginRecord(name=Path(filename).stem, file=filename,
                             error="Missing PLUGIN dict constant.")

    name = plugin_meta.get("name")
    if not isinstance(name, str) or not _NAME_RE.match(name):
        return PluginRecord(name=str(name or Path(filename).stem), file=filename,
                             error="PLUGIN['name'] missing or not a valid identifier "
                                   "(letters/digits/underscore, must start with letter/underscore).")

    description = plugin_meta.get("description")
    if not isinstance(description, str) or not description.strip():
        return PluginRecord(name=name, file=filename,
                             error="PLUGIN['description'] missing or empty.")

    parameters = plugin_meta.get("parameters", _DEFAULT_PARAMS)
    if not isinstance(parameters, dict) or parameters.get("type") != "OBJECT":
        return PluginRecord(name=name, file=filename,
                             error="PLUGIN['parameters'] must be a dict with \"type\": \"OBJECT\".")

    run_fn = getattr(module, "run", None)
    if not callable(run_fn):
        return PluginRecord(name=name, file=filename,
                             error="Missing callable run(parameters, ...) function.")

    # Optional, self-describing settings schema (rendered by the settings UI).
    # A malformed schema is ignored, never fatal — the plugin still loads.
    settings = getattr(module, "PLUGIN_SETTINGS", None)
    if not (isinstance(settings, dict) and isinstance(settings.get("fields"), list)):
        settings = None

    # Phase 2: Validate capabilities
    capabilities = plugin_meta.get("capabilities", [])
    if not isinstance(capabilities, list):
        capabilities = []
    invalid_caps = [c for c in capabilities if c not in _VALID_CAPABILITIES]
    if invalid_caps:
        # Warning only, not fatal - log and continue
        pass  # will be logged by caller

    # Phase 2: Sandbox config
    sandboxed = bool(plugin_meta.get("sandboxed", False))
    sandbox_timeout = int(plugin_meta.get("sandbox_timeout", 30))
    sandbox_memory_mb = int(plugin_meta.get("sandbox_memory_mb", 256))

    # Phase 2: Enhanced metadata
    version = str(plugin_meta.get("version", "1.0.0"))
    author = str(plugin_meta.get("author", ""))
    license_ = str(plugin_meta.get("license", "MIT"))
    homepage = str(plugin_meta.get("homepage", ""))
    repository = str(plugin_meta.get("repository", ""))
    keywords = plugin_meta.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []
    dependencies = plugin_meta.get("dependencies", [])
    if not isinstance(dependencies, list):
        dependencies = []
    min_jarvis_version = str(plugin_meta.get("min_jarvis_version", "1.0.0"))

    return PluginRecord(name=name, description=description.strip(), parameters=parameters,
                         run=run_fn, file=filename, valid=True, error="", settings=settings,
                         behavior=_opt_upper(plugin_meta.get("behavior"), _BEHAVIORS),
                         scheduling=_opt_upper(plugin_meta.get("scheduling"), _SCHEDULING),
                         tier=_opt_tier(plugin_meta.get("tier")),
                         brief=_opt_text(plugin_meta.get("brief")),
                         version=version, author=author, license=license_,
                         homepage=homepage, repository=repository,
                         keywords=keywords, dependencies=dependencies,
                         min_jarvis_version=min_jarvis_version,
                         capabilities=capabilities,
                         sandboxed=sandboxed,
                         sandbox_timeout=sandbox_timeout,
                         sandbox_memory_mb=sandbox_memory_mb)


# The app's own top-level packages. Named explicitly rather than only probed on
# disk, because the case that matters most is the folder being ABSENT: a plugin
# importing core.undo on a build with no core/ at all must still be told to
# update, not to install something called "core".
_FIRST_PARTY = {"core", "memory", "actions", "plugins", "dashboard", "config"}


def _is_first_party(top: str, plugins_dir: Path) -> bool:
    """True when `top` names part of this app rather than a third-party package.

    The disk probe is the second half so a package added to the project later is
    recognised without anyone remembering to edit the set above.
    """
    if top in _FIRST_PARTY:
        return True
    root = plugins_dir.parent
    try:
        return (root / top).is_dir() or (root / f"{top}.py").is_file()
    except OSError:
        return False


def _load_error(path: Path, plugins_dir: Path, exc: Exception) -> str:
    """Turn an import failure into something the person who downloaded the file
    can act on.

    Plugins are shared one file at a time, but some of them sit on a helper —
    anything named with a leading underscore, which this loader deliberately
    skips so it is never treated as a plugin of its own. Download the plugin
    without its helper and Python reports `No module named 'plugins._x'`, which
    is accurate and tells a non-programmer nothing. Naming the missing file, and
    saying it belongs next to this one, turns a support question into a
    thirty-second fix. Nothing here is specific to any plugin: the helper's name
    comes from the exception itself.
    """
    if isinstance(exc, ModuleNotFoundError):
        missing = (getattr(exc, "name", "") or "").split(".")
        if len(missing) == 2 and missing[0] == "plugins" and missing[1].startswith("_"):
            helper = missing[1] + ".py"
            return (f"Needs the shared file '{helper}', which is not in "
                    f"{plugins_dir.name}/. It comes with this plugin — download "
                    f"'{helper}' into the same folder as {path.name} and restart.")
        if missing and missing[0] not in ("plugins",):
            if _is_first_party(missing[0], plugins_dir):
                # 'pip install core' is not merely unhelpful — it is dangerous
                # advice. These names belong to this project, and telling
                # somebody to install a same-named stranger from an index is a
                # supply-chain hazard dressed up as a fix. A plugin written
                # against a newer Mark reaches this line, and the honest answer
                # is that the app is behind the plugin, not that a package is
                # absent.
                needed = "/".join(missing) + ".py"
                return (f"Needs '{needed}', which is part of this app rather than "
                        f"something to install — your copy doesn't have it, so it "
                        f"comes with a newer version. Update the app; there is "
                        f"nothing to pip install.")
            return (f"Needs a package that is not installed: "
                    f"pip install {missing[0]}")
    return f"Failed to load: {exc}"


def discover_plugins(plugins_dir: Path, core_tool_names: set[str],
                      logger: Callable[[str], None] = print,
                      notify: Callable[[str], None] | None = None) -> PluginRegistry:
    """
    Scans plugins_dir for *.py files (skips files starting with '_', e.g. __init__.py,
    _template.py, and any shared-helper modules an author prefixes with '_').
    Import errors, validation errors, and name collisions are logged and the offending
    file is skipped — they NEVER raise out of this function and never abort the scan
    of remaining files.
    """
    plugins_dir.mkdir(parents=True, exist_ok=True)
    valid: dict[str, PluginRecord] = {}
    all_records: list[PluginRecord] = []

    files = sorted(plugins_dir.glob("*.py"), key=lambda p: p.name)  # deterministic order
    for path in files:
        if path.name.startswith("_"):
            continue
        try:
            module_name = f"plugins.{path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError("could not build import spec")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(module_name, None)
                raise

            rec = _validate(module, path.name)

            if rec.valid and rec.name in core_tool_names:
                rec = PluginRecord(name=rec.name, file=path.name,
                                    error=f"Name '{rec.name}' collides with a core tool — rejected.")
            elif rec.valid and rec.name in valid:
                other = valid[rec.name].file
                rec = PluginRecord(name=rec.name, file=path.name,
                                    error=f"Name '{rec.name}' already used by plugin '{other}' — rejected.")

        except Exception as e:
            rec = PluginRecord(name=path.stem, file=path.name,
                                error=_load_error(path, plugins_dir, e))
            traceback.print_exc()

        all_records.append(rec)
        if rec.valid:
            # Set initial _last_modified from file mtime
            rec._last_modified = path.stat().st_mtime
            valid[rec.name] = rec
            logger(f"Plugin loaded: {rec.name} ({path.name})")
            # Call on_load hook after plugin is registered
            # We need to call this after the registry is created, so we'll do it later
        else:
            logger(f"Plugin rejected: {path.name} — {rec.error}")

    notify = notify or (lambda _msg: None)
    registry = PluginRegistry(valid, logger, notify)
    registry._all_records = all_records

    # Phase 2: Call on_load hooks for all valid plugins
    for rec in valid.values():
        registry._call_lifecycle_hook(rec, "on_load")

    # Phase 2: Load granted capabilities from config
    registry.load_granted_capabilities()

    # Phase 2: Check plugin dependencies
    missing_deps = registry.check_all_dependencies()
    for plugin_name, missing in missing_deps.items():
        logger(f"[SYS] [PluginLoader] Plugin '{plugin_name}' missing dependencies: {', '.join(missing)}")

    # Phase 2: Start hot-reload watcher
    registry.start_hot_reload(plugins_dir, core_tool_names)

    rejected = len(all_records) - len(valid)
    logger(f"Plugin discovery complete: {len(valid)} active, "
           f"{rejected} rejected, {len(all_records)} total.")
    # The activity log is the user's conversation, not a boot transcript: a
    # plugin that loaded correctly is not news, so only a failure surfaces there
    # — and then as one line, because the per-plugin detail is on the console.
    if rejected:
        notify(f"{rejected} plugin(s) could not be loaded — see the console.")
    return registry
