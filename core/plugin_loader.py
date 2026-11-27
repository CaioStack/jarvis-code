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

    # Phase 2: Rate limiting
    rate_limit: int = 0  # max calls per minute (0 = unlimited)
    _call_timestamps: list = field(default_factory=list, repr=False)  # recent call times

    # Phase 2: Plugin signing/verification
    signature: str = ""  # cryptographic signature
    signer: str = ""     # who signed it
    verified: bool = False  # signature verification result

    # Phase 2: Categorization and favorites
    category: str = ""   # plugin category (utility, media, system, ai, etc.)
    tags: list[str] = field(default_factory=list)  # user-defined tags
    favorite: bool = False  # user marked as favorite

    # Phase 2: Priority/ordering
    priority: int = 0  # execution priority (higher = runs first), 0 = default

    # Phase 2: Circuit breaker
    circuit_breaker_threshold: int = 5  # failures before opening circuit
    circuit_breaker_timeout: int = 60   # seconds before half-open
    _failure_streak: int = 0
    _circuit_open_at: float = 0
    _circuit_state: str = "closed"  # closed, open, half-open

    # Phase 2: Retry policy
    max_retries: int = 0
    retry_delay: float = 1.0
    retry_backoff: float = 2.0

    # Phase 2: Resource quotas
    cpu_quota_percent: float = 0.0  # 0 = unlimited
    memory_quota_mb: int = 0        # 0 = unlimited
    disk_quota_mb: int = 0          # 0 = unlimited

    # Phase 2: Audit logging
    audit_log: bool = False


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

        # Phase 2: Global event hooks
        self._hooks: dict[str, list[Callable]] = {
            "plugin_loaded": [],
            "plugin_unloaded": [],
            "plugin_enabled": [],
            "plugin_disabled": [],
            "plugin_reloaded": [],
            "plugin_error": [],
            "before_run": [],
            "after_run": [],
        }

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

    # Phase 2: Global event hooks
    def register_hook(self, event: str, callback: Callable) -> bool:
        """Register a global event hook.

        Events: plugin_loaded, plugin_unloaded, plugin_enabled, plugin_disabled,
                plugin_reloaded, plugin_error, before_run, after_run
        """
        if event in self._hooks:
            self._hooks[event].append(callback)
            return True
        return False

    def unregister_hook(self, event: str, callback: Callable) -> bool:
        """Unregister a global event hook."""
        if event in self._hooks and callback in self._hooks[event]:
            self._hooks[event].remove(callback)
            return True
        return False

    def _trigger_hook(self, event: str, *args, **kwargs) -> None:
        """Trigger all callbacks for an event."""
        if event in self._hooks:
            for callback in self._hooks[event]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    self._logger(f"[SYS] [PluginLoader] Hook '{event}' failed: {e}")

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

        # Phase 2: Rate limiting
        if rec.rate_limit > 0:
            import time
            now = time.time()
            # Remove timestamps older than 1 minute
            rec._call_timestamps = [ts for ts in rec._call_timestamps if now - ts < 60]
            if len(rec._call_timestamps) >= rec.rate_limit:
                self._logger(f"[SYS] [PluginLoader] Plugin '{name}' rate limited ({rec.rate_limit}/min)")
                return f"Plugin '{name}' rate limit exceeded ({rec.rate_limit} calls/minute). Please wait."
            rec._call_timestamps.append(now)

        # Phase 2: Resource quota enforcement
        import time
        import os
        try:
            if rec.cpu_quota_percent > 0 or rec.memory_quota_mb > 0 or rec.disk_quota_mb > 0:
                import psutil
                process = psutil.Process()

                # Check CPU quota
                if rec.cpu_quota_percent > 0:
                    cpu_percent = process.cpu_percent(interval=0.1)
                    if cpu_percent > rec.cpu_quota_percent:
                        return f"Plugin '{name}' exceeded CPU quota ({cpu_percent:.1f}% > {rec.cpu_quota_percent}%)."

                # Check memory quota
                if rec.memory_quota_mb > 0:
                    mem_info = process.memory_info()
                    mem_mb = mem_info.rss / (1024 * 1024)
                    if mem_mb > rec.memory_quota_mb:
                        return f"Plugin '{name}' exceeded memory quota ({mem_mb:.1f}MB > {rec.memory_quota_mb}MB)."

                # Check disk quota (approximate - check current working directory)
                if rec.disk_quota_mb > 0:
                    try:
                        stat = os.statvfs('.')
                        free_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
                        # This is a rough check - in practice you'd track plugin-specific disk usage
                        if free_mb < rec.disk_quota_mb:
                            return f"Plugin '{name}' disk quota check failed: only {free_mb:.1f}MB free (need {rec.disk_quota_mb}MB)."
                    except Exception:
                        pass  # Disk quota check failed, continue anyway
        except ImportError:
            self._logger(f"[SYS] [PluginLoader] psutil not available, skipping resource quota checks for '{name}'")
        except Exception as e:
            self._logger(f"[SYS] [PluginLoader] Resource quota check failed for '{name}': {e}")

        # Phase 2: Debug logging
        if rec.debug:
            self._logger(f"[SYS] [PluginLoader] DEBUG: Running '{name}' with params: {parameters}")

        # Phase 2: Circuit breaker check
        if rec._circuit_state == "open":
            import time
            if time.time() - rec._circuit_open_at >= rec.circuit_breaker_timeout:
                rec._circuit_state = "half-open"
                self._logger(f"[SYS] [PluginLoader] Circuit breaker for '{name}' moved to half-open")
            else:
                return f"Plugin '{name}' circuit breaker is OPEN. Try again later."
        elif rec._circuit_state == "half-open":
            # Allow one request through in half-open state
            pass

        # Phase 2: Performance tracking
        import time
        start_time = time.perf_counter()
        now = time.time()
        rec._last_run = now

        # Track first run
        if rec._first_run == 0:
            rec._first_run = now

        # Phase 2: Trigger before_run hook
        self._trigger_hook("before_run", name, parameters)

        # Phase 2: Retry logic
        last_error = None
        for attempt in range(rec.max_retries + 1):
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

                # Phase 2: Circuit breaker - reset failure streak on success
                rec._failure_streak = 0
                if rec._circuit_state == "half-open":
                    rec._circuit_state = "closed"
                    self._logger(f"[SYS] [PluginLoader] Circuit breaker for '{name}' CLOSED")

                # Phase 2: Trigger after_run hook
                self._trigger_hook("after_run", name, parameters, result, elapsed)

                # Phase 2: Debug logging for result
                if rec.debug:
                    self._logger(f"[SYS] [PluginLoader] DEBUG: '{name}' completed in {elapsed*1000:.2f}ms: {result[:100]}")

                # Phase 2: Audit logging
                if rec.audit_log:
                    self._logger(f"[AUDIT] Plugin '{name}' executed successfully | params={parameters} | result={result[:200]} | elapsed={elapsed*1000:.2f}ms")

                return result

            except Exception as e:
                last_error = e
                elapsed = time.perf_counter() - start_time

                # Phase 2: Circuit breaker - increment failure streak
                rec._failure_streak += 1
                if rec._failure_streak >= rec.circuit_breaker_threshold:
                    rec._circuit_state = "open"
                    rec._circuit_open_at = time.time()
                    self._logger(f"[SYS] [PluginLoader] Circuit breaker for '{name}' OPENED after {rec._failure_streak} failures")

                if attempt < rec.max_retries:
                    # Wait before retry with exponential backoff
                    import time
                    wait_time = rec.retry_delay * (rec.retry_backoff ** attempt)
                    self._logger(f"[SYS] [PluginLoader] Plugin '{name}' attempt {attempt + 1} failed, retrying in {wait_time:.1f}s: {e}")
                    time.sleep(wait_time)
                    continue
                else:
                    # All retries exhausted
                    rec._run_count += 1
                    rec._total_run_time += elapsed
                    rec._last_run_time = elapsed
                    rec._last_error = str(e)
                    rec._failure_count += 1
                    rec._last_failure = now

                    # Phase 2: Trigger plugin_error hook
                    self._trigger_hook("plugin_error", name, e)

                    # Phase 2: Audit logging for failures
                    if rec.audit_log:
                        self._logger(f"[AUDIT] Plugin '{name}' FAILED | params={parameters} | error={e} | elapsed={elapsed*1000:.2f}ms | attempt={attempt+1}/{rec.max_retries+1}")

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

    # Phase 2: Categorization and favorites
    def set_category(self, plugin_name: str, category: str) -> bool:
        """Set a plugin's category."""
        rec = self._plugins.get(plugin_name)
        if rec:
            rec.category = category
            self._logger(f"[SYS] [PluginLoader] Category set for '{plugin_name}': {category}")
            return True
        return False

    def add_tag(self, plugin_name: str, tag: str) -> bool:
        """Add a tag to a plugin."""
        rec = self._plugins.get(plugin_name)
        if rec and tag not in rec.tags:
            rec.tags.append(tag)
            self._logger(f"[SYS] [PluginLoader] Tag added to '{plugin_name}': {tag}")
            return True
        return False

    def remove_tag(self, plugin_name: str, tag: str) -> bool:
        """Remove a tag from a plugin."""
        rec = self._plugins.get(plugin_name)
        if rec and tag in rec.tags:
            rec.tags.remove(tag)
            self._logger(f"[SYS] [PluginLoader] Tag removed from '{plugin_name}': {tag}")
            return True
        return False

    def toggle_favorite(self, plugin_name: str) -> bool:
        """Toggle a plugin's favorite status."""
        rec = self._plugins.get(plugin_name)
        if rec:
            rec.favorite = not rec.favorite
            status = "added to" if rec.favorite else "removed from"
            self._logger(f"[SYS] [PluginLoader] Plugin '{plugin_name}' {status} favorites")
            return True
        return False

    def get_favorites(self) -> list[str]:
        """Get list of favorite plugin names."""
        return [name for name, rec in self._plugins.items() if rec.favorite]

    def get_by_category(self, category: str) -> list[str]:
        """Get plugin names by category."""
        return [name for name, rec in self._plugins.items() if rec.category == category]

    def get_by_tag(self, tag: str) -> list[str]:
        """Get plugin names by tag."""
        return [name for name, rec in self._plugins.items() if tag in rec.tags]

    # Phase 2: Priority/ordering
    def set_priority(self, plugin_name: str, priority: int) -> bool:
        """Set a plugin's execution priority (higher = runs first)."""
        rec = self._plugins.get(plugin_name)
        if rec:
            rec.priority = int(priority)
            self._logger(f"[SYS] [PluginLoader] Priority set for '{plugin_name}': {priority}")
            return True
        return False

    def get_sorted_plugins(self, reverse: bool = True) -> list[str]:
        """Get plugin names sorted by priority (highest first by default)."""
        return sorted(
            self._plugins.keys(),
            key=lambda n: self._plugins[n].priority,
            reverse=reverse
        )

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

    # Phase 2: Plugin signing/verification (HMAC-based, for backward compatibility)
    def verify_plugin_signature(self, plugin_name: str, public_key: str = None) -> dict:
        """Verify a plugin's cryptographic signature.

        For simplicity, this uses a basic hash-based verification.
        In production, use proper cryptographic signatures (Ed25519, RSA).
        """
        import hashlib
        import hmac

        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"verified": False, "error": f"Plugin '{plugin_name}' not found"}

        if not rec.signature or not rec.signer:
            return {
                "verified": False,
                "error": "Plugin not signed (no signature or signer)",
                "signer": rec.signer,
            }

        # Read plugin source and compute hash
        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return {"verified": False, "error": "Plugin module not loaded"}

        import inspect
        source = inspect.getsource(module)

        # Compute hash of source code
        expected_hash = hashlib.sha256(source.encode()).hexdigest()

        # For demo: signature is HMAC of hash with a shared secret
        # In production, verify actual cryptographic signature
        if public_key:
            # Verify using provided public key (simplified)
            computed = hmac.new(public_key.encode(), expected_hash.encode(), hashlib.sha256).hexdigest()
        else:
            # No public key provided - just check if signature matches computed hash
            computed = expected_hash

        verified = hmac.compare_digest(rec.signature, computed)

        return {
            "verified": verified,
            "signer": rec.signer,
            "signature": rec.signature[:16] + "...",
            "expected_hash": expected_hash[:16] + "...",
            "verified_at": time.time(),
        }

    def sign_plugin(self, plugin_name: str, private_key: str, signer: str) -> bool:
        """Sign a plugin with a private key (for development/trusted plugins).

        Returns True if signing succeeded.
        """
        import hmac
        import hashlib

        rec = self._plugins.get(plugin_name)
        if not rec:
            return False

        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return False

        import inspect
        source = inspect.getsource(module)
        source_hash = hashlib.sha256(source.encode()).hexdigest()

        # Sign with HMAC (simplified - use proper crypto in production)
        signature = hmac.new(private_key.encode(), source_hash.encode(), hashlib.sha256).hexdigest()

        rec.signature = signature
        rec.signer = signer
        rec.verified = True

        self._logger(f"[SYS] [PluginLoader] Plugin '{plugin_name}' signed by '{signer}'")
        return True

    # Phase 2: Ed25519 cryptographic signing (production-ready)
    def sign_plugin_ed25519(self, plugin_name: str, private_key_bytes: bytes, signer: str) -> bool:
        """Sign a plugin using Ed25519 (production-ready cryptographic signing).

        Args:
            plugin_name: Name of the plugin to sign
            private_key_bytes: 32-byte Ed25519 private key
            signer: Identity of the signer

        Returns True if signing succeeded.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.hazmat.primitives import serialization
        except ImportError:
            self._logger("[SYS] [PluginLoader] cryptography package not available for Ed25519 signing")
            return False

        rec = self._plugins.get(plugin_name)
        if not rec:
            return False

        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return False

        import inspect
        source = inspect.getsource(module)
        source_hash = hashlib.sha256(source.encode()).digest()

        # Sign with Ed25519
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        signature = private_key.sign(source_hash)

        rec.signature = signature.hex()
        rec.signer = signer
        rec.verified = True

        self._logger(f"[SYS] [PluginLoader] Plugin '{plugin_name}' signed with Ed25519 by '{signer}'")
        return True

    def verify_plugin_ed25519(self, plugin_name: str, public_key_bytes: bytes) -> dict:
        """Verify a plugin's Ed25519 signature.

        Args:
            plugin_name: Name of the plugin to verify
            public_key_bytes: 32-byte Ed25519 public key

        Returns dict with verification result.
        """
        try:
            from cryptography.hazmat.primitives.asymmetric import ed25519
            from cryptography.exceptions import InvalidSignature
        except ImportError:
            return {"verified": False, "error": "cryptography package not available"}

        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"verified": False, "error": f"Plugin '{plugin_name}' not found"}

        if not rec.signature:
            return {"verified": False, "error": "Plugin not signed"}

        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return {"verified": False, "error": "Plugin module not loaded"}

        import inspect
        import hashlib
        source = inspect.getsource(module)
        source_hash = hashlib.sha256(source.encode()).digest()

        # Verify Ed25519 signature
        try:
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(bytes.fromhex(rec.signature), source_hash)
            verified = True
        except InvalidSignature:
            verified = False
        except Exception as e:
            return {"verified": False, "error": f"Verification error: {e}"}

        rec.verified = verified

        return {
            "verified": verified,
            "signer": rec.signer,
            "signature": rec.signature[:16] + "...",
            "verified_at": time.time(),
        }

    # Phase 2: Plugin update checking
    def check_plugin_updates(self, plugin_name: str, repository_url: str = None) -> dict:
        """Check if a plugin has updates available from its repository.

        Args:
            plugin_name: Name of the plugin to check
            repository_url: Optional repository URL (uses plugin's repository if not provided)

        Returns dict with: has_update, current_version, latest_version, changelog_url
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"error": f"Plugin '{plugin_name}' not found"}

        repo = repository_url or rec.repository
        if not repo:
            return {"error": "No repository URL configured for this plugin"}

        # For GitHub repositories, check latest release
        if "github.com" in repo:
            return self._check_github_updates(plugin_name, repo, rec.version)

        return {"error": f"Unsupported repository type: {repo}"}

    def _check_github_updates(self, plugin_name: str, repo_url: str, current_version: str) -> dict:
        """Check GitHub releases for plugin updates."""
        import re
        try:
            import httpx
        except ImportError:
            return {"error": "httpx not available for update checking"}

        # Extract owner/repo from URL
        match = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", repo_url)
        if not match:
            return {"error": "Invalid GitHub repository URL"}

        owner, repo = match.groups()
        repo = repo.replace(".git", "")

        try:
            response = httpx.get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", timeout=10)
            if response.status_code != 200:
                return {"error": f"GitHub API error: {response.status_code}"}

            release = response.json()
            latest_version = release.get("tag_name", "").lstrip("v")

            # Simple version comparison
            def parse_version(v):
                parts = v.split('.')
                return tuple(int(p) for p in parts[:3])

            current = parse_version(current_version)
            latest = parse_version(latest_version)

            has_update = latest > current

            return {
                "has_update": has_update,
                "current_version": current_version,
                "latest_version": latest_version,
                "release_url": release.get("html_url"),
                "changelog": release.get("body", "")[:500],
                "published_at": release.get("published_at"),
            }
        except Exception as e:
            return {"error": f"Update check failed: {e}"}

    def check_all_plugin_updates(self) -> dict:
        """Check all plugins for updates."""
        results = {}
        for name, rec in self._plugins.items():
            if rec.repository:
                results[name] = self.check_plugin_updates(name)
            else:
                results[name] = {"skipped": True, "reason": "No repository URL"}
        return results

    # Phase 2: Auto-install plugin dependencies
    def install_plugin_dependencies(self, plugin_name: str) -> dict:
        """Attempt to install missing pip dependencies for a plugin.

        Returns dict with: success, installed, failed, message
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"error": f"Plugin '{plugin_name}' not found"}

        if not rec.dependencies:
            return {"success": True, "message": "No dependencies declared"}

        import subprocess
        import sys

        missing = []
        for dep in rec.dependencies:
            try:
                __import__(dep.replace('-', '_'))
            except ImportError:
                missing.append(dep)

        if not missing:
            return {"success": True, "message": "All dependencies already installed"}

        installed = []
        failed = []

        for dep in missing:
            try:
                self._logger(f"[SYS] [PluginLoader] Installing dependency '{dep}' for '{plugin_name}'")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0:
                    installed.append(dep)
                else:
                    failed.append(dep)
                    self._logger(f"[SYS] [PluginLoader] Failed to install '{dep}': {result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                failed.append(dep)
                self._logger(f"[SYS] [PluginLoader] Timeout installing '{dep}'")
            except Exception as e:
                failed.append(dep)
                self._logger(f"[SYS] [PluginLoader] Error installing '{dep}': {e}")

        success = len(failed) == 0
        return {
            "success": success,
            "installed": installed,
            "failed": failed,
            "message": f"Installed {len(installed)} of {len(missing)} missing dependencies"
        }

    def install_all_missing_dependencies(self) -> dict:
        """Install missing dependencies for all plugins."""
        results = {}
        for name, rec in self._plugins.items():
            if rec.dependencies:
                results[name] = self.install_plugin_dependencies(name)
        return results

    # Phase 2: Plugin permission presets
    def apply_capability_preset(self, plugin_name: str, preset: str) -> bool:
        """Apply a predefined capability preset to a plugin.

        Presets:
            - "minimal": ui.notify only
            - "filesystem": filesystem.read, filesystem.write, filesystem.list
            - "network": network.http, network.websocket
            - "system": shell.exec, process.spawn
            - "media": audio.record, audio.play, video.record
            - "data": memory.read, memory.write, config.read, config.write
            - "full": all capabilities
        """
        presets = {
            "minimal": ["ui.notify"],
            "filesystem": ["filesystem.read", "filesystem.write", "filesystem.list"],
            "network": ["network.http", "network.websocket"],
            "system": ["shell.exec", "process.spawn"],
            "media": ["audio.record", "audio.play", "video.record"],
            "data": ["memory.read", "memory.write", "config.read", "config.write"],
            "full": list(_VALID_CAPABILITIES),
        }

        if preset not in presets:
            return False

        rec = self._plugins.get(plugin_name)
        if not rec:
            return False

        rec.granted_capabilities = presets[preset]
        self._save_capabilities()
        self._logger(f"[SYS] [PluginLoader] Applied '{preset}' preset to '{plugin_name}'")
        return True

    def get_capability_presets(self) -> dict:
        """Get available capability presets."""
        return {
            "minimal": ["ui.notify"],
            "filesystem": ["filesystem.read", "filesystem.write", "filesystem.list"],
            "network": ["network.http", "network.websocket"],
            "system": ["shell.exec", "process.spawn"],
            "media": ["audio.record", "audio.play", "video.record"],
            "data": ["memory.read", "memory.write", "config.read", "config.write"],
            "full": list(_VALID_CAPABILITIES),
        }

    # Phase 2: Plugin scheduling/cron-like execution
    def schedule_plugin(self, plugin_name: str, cron_expression: str, parameters: dict = None) -> bool:
        """Schedule a plugin to run periodically using cron expression.

        Args:
            plugin_name: Name of the plugin to schedule
            cron_expression: Standard 5-field cron (e.g., "0 * * * *" = hourly)
            parameters: Parameters to pass to the plugin

        Returns True if scheduling succeeded.
        """
        try:
            from croniter import croniter
            # Validate cron expression
            croniter(cron_expression)
        except ImportError:
            self._logger("[SYS] [PluginLoader] croniter not available for scheduling")
            return False
        except Exception as e:
            self._logger(f"[SYS] [PluginLoader] Invalid cron expression: {e}")
            return False

        rec = self._plugins.get(plugin_name)
        if not rec or not rec.valid:
            return False

        # Store schedule in plugin config
        from memory.config_manager import get_plugin_config, save_plugin_config
        config = get_plugin_config(plugin_name)
        if "schedules" not in config:
            config["schedules"] = []
        config["schedules"].append({
            "cron": cron_expression,
            "parameters": parameters or {},
            "enabled": True,
            "created_at": time.time(),
        })
        save_plugin_config(plugin_name, config)

        self._logger(f"[SYS] [PluginLoader] Scheduled '{plugin_name}' with cron '{cron_expression}'")
        return True

    def unschedule_plugin(self, plugin_name: str, cron_expression: str = None) -> bool:
        """Remove a scheduled plugin run.

        If cron_expression is provided, remove only that schedule.
        Otherwise, remove all schedules for the plugin.
        """
        from memory.config_manager import get_plugin_config, save_plugin_config
        config = get_plugin_config(plugin_name)
        schedules = config.get("schedules", [])

        if cron_expression:
            schedules = [s for s in schedules if s.get("cron") != cron_expression]
        else:
            schedules = []

        config["schedules"] = schedules
        save_plugin_config(plugin_name, config)
        return True

    def get_scheduled_plugins(self) -> dict:
        """Get all scheduled plugin runs."""
        from memory.config_manager import get_plugin_config
        scheduled = {}
        for name, rec in self._plugins.items():
            config = get_plugin_config(name)
            schedules = config.get("schedules", [])
            if schedules:
                scheduled[name] = schedules
        return scheduled

    def run_scheduled_plugins(self, player=None, session_memory=None) -> dict:
        """Check and run any scheduled plugins that are due.

        This should be called periodically (e.g., every minute) by the main app.
        Returns dict of plugin_name -> result for plugins that ran.
        """
        try:
            from croniter import croniter
        except ImportError:
            return {"error": "croniter not available"}

        import time
        now = time.time()
        results = {}

        scheduled = self.get_scheduled_plugins()
        for plugin_name, schedules in scheduled.items():
            for schedule in schedules:
                if not schedule.get("enabled", True):
                    continue

                cron_expr = schedule.get("cron")
                if not cron_expr:
                    continue

                try:
                    # Check if this schedule is due
                    cron = croniter(cron_expr, now - 60)  # Check last minute
                    next_run = cron.get_next(float)

                    # If next_run is within the last minute, it's due
                    if abs(next_run - now) < 60:
                        params = schedule.get("parameters", {})
                        result = self.run(plugin_name, params, player, session_memory)
                        results[plugin_name] = result
                        self._logger(f"[SYS] [PluginLoader] Ran scheduled plugin '{plugin_name}'")
                except Exception as e:
                    self._logger(f"[SYS] [PluginLoader] Scheduled plugin '{plugin_name}' failed: {e}")

        return results

    # Phase 2: Plugin profiling/performance analysis
    def profile_plugin(self, plugin_name: str, sample_parameters: dict = None,
                       iterations: int = 10, player=None, session_memory=None) -> dict:
        """Profile a plugin's performance over multiple runs.

        Args:
            plugin_name: Name of the plugin to profile
            sample_parameters: Parameters to use for profiling runs
            iterations: Number of profiling iterations
            player: Player instance
            session_memory: Session memory

        Returns dict with performance statistics.
        """
        rec = self._plugins.get(plugin_name)
        if not rec or not rec.valid:
            return {"error": f"Plugin '{plugin_name}' not found or invalid"}

        import time
        import statistics

        times = []
        errors = 0
        results = []

        for i in range(iterations):
            start = time.perf_counter()
            try:
                result = self.run(plugin_name, sample_parameters or {}, player, session_memory)
                elapsed = time.perf_counter() - start
                times.append(elapsed)
                results.append(result)
            except Exception as e:
                errors += 1
                results.append(str(e))

        if not times:
            return {"error": "All profiling runs failed"}

        return {
            "plugin": plugin_name,
            "iterations": iterations,
            "successful_runs": len(times),
            "errors": errors,
            "min_time": min(times),
            "max_time": max(times),
            "mean_time": statistics.mean(times),
            "median_time": statistics.median(times),
            "stdev_time": statistics.stdev(times) if len(times) > 1 else 0,
            "total_time": sum(times),
            "sample_results": results[:3],  # First 3 results
        }

    def get_plugin_profile(self, plugin_name: str) -> dict:
        """Get cached profile data for a plugin."""
        # This would be stored in config - for now return empty
        from memory.config_manager import get_plugin_config
        config = get_plugin_config(plugin_name)
        return config.get("profile", {})

    def save_plugin_profile(self, plugin_name: str, profile_data: dict) -> bool:
        """Save profile data for a plugin."""
        from memory.config_manager import get_plugin_config, save_plugin_config
        config = get_plugin_config(plugin_name)
        config["profile"] = profile_data
        config["profiled_at"] = time.time()
        save_plugin_config(plugin_name, config)
        return True

    # Phase 2: Plugin metrics export (Prometheus-compatible)
    def export_metrics_prometheus(self) -> str:
        """Export plugin metrics in Prometheus format.

        Returns string with metrics in Prometheus text format.
        """
        lines = [
            "# HELP jarvis_plugin_runs_total Total number of plugin runs",
            "# TYPE jarvis_plugin_runs_total counter",
        ]

        for name, rec in self._plugins.items():
            if rec.valid:
                lines.append(f'jarvis_plugin_runs_total{{plugin="{name}"}} {rec._run_count}')

        lines.extend([
            "",
            "# HELP jarvis_plugin_run_time_seconds Total time spent running plugins",
            "# TYPE jarvis_plugin_run_time_seconds counter",
        ])

        for name, rec in self._plugins.items():
            if rec.valid:
                lines.append(f'jarvis_plugin_run_time_seconds{{plugin="{name}"}} {rec._total_run_time}')

        lines.extend([
            "",
            "# HELP jarvis_plugin_success_rate Plugin success rate percentage",
            "# TYPE jarvis_plugin_success_rate gauge",
        ])

        for name, rec in self._plugins.items():
            if rec.valid and rec._run_count > 0:
                success_rate = (rec._success_count / rec._run_count) * 100
                lines.append(f'jarvis_plugin_success_rate{{plugin="{name}"}} {success_rate:.2f}')

        lines.extend([
            "",
            "# HELP jarvis_plugin_last_run_timestamp Unix timestamp of last plugin run",
            "# TYPE jarvis_plugin_last_run_timestamp gauge",
        ])

        for name, rec in self._plugins.items():
            if rec.valid and rec._last_run > 0:
                lines.append(f'jarvis_plugin_last_run_timestamp{{plugin="{name}"}} {rec._last_run}')

        lines.extend([
            "",
            "# HELP jarvis_plugin_circuit_state Circuit breaker state (0=closed, 1=half-open, 2=open)",
            "# TYPE jarvis_plugin_circuit_state gauge",
        ])

        state_map = {"closed": 0, "half-open": 1, "open": 2}
        for name, rec in self._plugins.items():
            if rec.valid:
                state = state_map.get(rec._circuit_state, 0)
                lines.append(f'jarvis_plugin_circuit_state{{plugin="{name}"}} {state}')

        lines.extend([
            "",
            "# HELP jarvis_plugin_reload_count Number of times plugin was hot-reloaded",
            "# TYPE jarvis_plugin_reload_count counter",
        ])

        for name, rec in self._plugins.items():
            if rec.valid:
                lines.append(f'jarvis_plugin_reload_count{{plugin="{name}"}} {rec._reload_count}')

        return "\n".join(lines)

    # Phase 2: Plugin rollback/versioning
    def create_plugin_snapshot(self, plugin_name: str) -> dict:
        """Create a snapshot of a plugin's current state for rollback.

        Returns snapshot dict with plugin state.
        """
        rec = self._plugins.get(plugin_name)
        if not rec:
            return {"error": f"Plugin '{plugin_name}' not found"}

        module_name = f"plugins.{rec.name}"
        import sys
        module = sys.modules.get(module_name)
        if not module:
            return {"error": "Plugin module not loaded"}

        import inspect
        source = inspect.getsource(module)

        snapshot = {
            "plugin_name": plugin_name,
            "version": rec.version,
            "source_code": source,
            "granted_capabilities": rec.granted_capabilities.copy(),
            "debug": rec.debug,
            "sandboxed": rec.sandboxed,
            "sandbox_timeout": rec.sandbox_timeout,
            "sandbox_memory_mb": rec.sandbox_memory_mb,
            "priority": rec.priority,
            "category": rec.category,
            "tags": rec.tags.copy(),
            "favorite": rec.favorite,
            "created_at": time.time(),
        }

        # Store in plugin config
        from memory.config_manager import get_plugin_config, save_plugin_config
        config = get_plugin_config(plugin_name)
        if "snapshots" not in config:
            config["snapshots"] = []
        config["snapshots"].append(snapshot)
        # Keep only last 10 snapshots
        config["snapshots"] = config["snapshots"][-10:]
        save_plugin_config(plugin_name, config)

        self._logger(f"[SYS] [PluginLoader] Created snapshot for '{plugin_name}'")
        return snapshot

    def rollback_plugin(self, plugin_name: str, snapshot_index: int = -1) -> bool:
        """Rollback a plugin to a previous snapshot.

        Args:
            plugin_name: Name of the plugin to rollback
            snapshot_index: Index of snapshot to rollback to (-1 = latest)

        Returns True if rollback succeeded.
        """
        from memory.config_manager import get_plugin_config, save_plugin_config
        config = get_plugin_config(plugin_name)
        snapshots = config.get("snapshots", [])

        if not snapshots:
            return False

        snapshot = snapshots[snapshot_index]

        # Apply snapshot settings
        rec = self._plugins.get(plugin_name)
        if not rec:
            return False

        rec.granted_capabilities = snapshot.get("granted_capabilities", [])
        rec.debug = snapshot.get("debug", False)
        rec.sandboxed = snapshot.get("sandboxed", False)
        rec.sandbox_timeout = snapshot.get("sandbox_timeout", 30)
        rec.sandbox_memory_mb = snapshot.get("sandbox_memory_mb", 256)
        rec.priority = snapshot.get("priority", 0)
        rec.category = snapshot.get("category", "")
        rec.tags = snapshot.get("tags", [])
        rec.favorite = snapshot.get("favorite", False)

        self._save_capabilities()

        self._logger(f"[SYS] [PluginLoader] Rolled back '{plugin_name}' to snapshot from {snapshot.get('created_at')}")
        return True

    def list_plugin_snapshots(self, plugin_name: str) -> list:
        """List available snapshots for a plugin."""
        from memory.config_manager import get_plugin_config
        config = get_plugin_config(plugin_name)
        snapshots = config.get("snapshots", [])
        return [
            {
                "index": i,
                "version": s.get("version"),
                "created_at": s.get("created_at"),
                "granted_capabilities": s.get("granted_capabilities", []),
            }
            for i, s in enumerate(snapshots)
        ]


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
