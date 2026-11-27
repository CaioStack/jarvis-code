"""
Unit tests for the Phase 2 Plugin System.
Run with: pytest tests/test_plugin_loader.py -v
"""

import pytest
import tempfile
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.plugin_loader import (
    PluginRecord,
    PluginRegistry,
    _VALID_CAPABILITIES,
    _CAPABILITY_GROUPS,
    discover_plugins,
    _validate,
)


class TestPluginRecord:
    """Test PluginRecord dataclass."""

    def test_default_values(self):
        """Test default values for PluginRecord."""
        rec = PluginRecord(name="test", description="Test plugin")
        assert rec.name == "test"
        assert rec.description == "Test plugin"
        assert rec.version == "1.0.0"
        assert rec.author == ""
        assert rec.capabilities == []
        assert rec.granted_capabilities == []
        assert rec.sandboxed is False
        assert rec.debug is False
        assert rec.rate_limit == 0
        assert rec.audit_log is False

    def test_phase2_fields(self):
        """Test Phase 2 specific fields."""
        rec = PluginRecord(
            name="test",
            description="Test",
            version="2.0.0",
            author="Test Author",
            license="MIT",
            homepage="https://example.com",
            repository="https://github.com/test/repo",
            keywords=["test", "plugin"],
            dependencies=["requests"],
            min_jarvis_version="1.2.0",
            capabilities=["network.http", "filesystem.read"],
            sandboxed=True,
            sandbox_timeout=30,
            sandbox_memory_mb=256,
            cpu_quota_percent=50.0,
            memory_quota_mb=200,
            disk_quota_mb=100,
            audit_log=True,
            rate_limit=10,
            debug=True,
            circuit_breaker_threshold=5,
            circuit_breaker_timeout=60,
            max_retries=3,
            retry_delay=1.0,
            retry_backoff=2.0,
            category="utility",
            tags=["tag1", "tag2"],
            favorite=True,
            priority=10,
        )

        assert rec.version == "2.0.0"
        assert rec.author == "Test Author"
        assert rec.license == "MIT"
        assert rec.homepage == "https://example.com"
        assert rec.repository == "https://github.com/test/repo"
        assert rec.keywords == ["test", "plugin"]
        assert rec.dependencies == ["requests"]
        assert rec.min_jarvis_version == "1.2.0"
        assert rec.capabilities == ["network.http", "filesystem.read"]
        assert rec.sandboxed is True
        assert rec.sandbox_timeout == 30
        assert rec.sandbox_memory_mb == 256
        assert rec.cpu_quota_percent == 50.0
        assert rec.memory_quota_mb == 200
        assert rec.disk_quota_mb == 100
        assert rec.audit_log is True
        assert rec.rate_limit == 10
        assert rec.debug is True
        assert rec.circuit_breaker_threshold == 5
        assert rec.circuit_breaker_timeout == 60
        assert rec.max_retries == 3
        assert rec.retry_delay == 1.0
        assert rec.retry_backoff == 2.0
        assert rec.category == "utility"
        assert rec.tags == ["tag1", "tag2"]
        assert rec.favorite is True
        assert rec.priority == 10


class TestCapabilities:
    """Test capability system."""

    def test_valid_capabilities_count(self):
        """Test that we have 14 valid capabilities."""
        assert len(_VALID_CAPABILITIES) == 14

    def test_capability_groups(self):
        """Test capability groups."""
        assert len(_CAPABILITY_GROUPS) == 7
        assert "Filesystem" in _CAPABILITY_GROUPS
        assert "Network" in _CAPABILITY_GROUPS
        assert "System" in _CAPABILITY_GROUPS
        assert "UI/Input" in _CAPABILITY_GROUPS
        assert "Media" in _CAPABILITY_GROUPS
        assert "Data" in _CAPABILITY_GROUPS
        assert "Plugins" in _CAPABILITY_GROUPS

    def test_filesystem_group(self):
        """Test filesystem capability group."""
        fs_caps = _CAPABILITY_GROUPS["Filesystem"]
        assert "filesystem.read" in fs_caps
        assert "filesystem.write" in fs_caps
        assert "filesystem.delete" in fs_caps
        assert "filesystem.list" in fs_caps

    def test_network_group(self):
        """Test network capability group."""
        net_caps = _CAPABILITY_GROUPS["Network"]
        assert "network.http" in net_caps
        assert "network.websocket" in net_caps
        assert "network.raw" in net_caps


class TestPluginValidation:
    """Test plugin validation."""

    def test_valid_plugin(self):
        """Test validation of a valid plugin module."""
        # Create a temporary plugin file
        plugin_code = '''
PLUGIN = {
    "name": "test_plugin",
    "version": "1.0.0",
    "description": "A test plugin",
    "parameters": {"type": "OBJECT", "properties": {}},
    "capabilities": ["ui.notify"],
}
def run(parameters, player=None, session_memory=None):
    return "Test result"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.test_plugin"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            rec = _validate(module, "test_plugin.py")
            assert rec.valid is True
            assert rec.name == "test_plugin"
            assert rec.version == "1.0.0"
            assert rec.capabilities == ["ui.notify"]
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)

    def test_missing_plugin_dict(self):
        """Test validation fails with missing PLUGIN dict."""
        plugin_code = '''
def run(parameters):
    return "Test"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.test_plugin"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            rec = _validate(module, "test_plugin.py")
            assert rec.valid is False
            assert "Missing PLUGIN dict" in rec.error
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)

    def test_invalid_name(self):
        """Test validation fails with invalid name."""
        plugin_code = '''
PLUGIN = {
    "name": "123invalid",
    "description": "Test",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters):
    return "Test"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.test_plugin"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            rec = _validate(module, "test_plugin.py")
            assert rec.valid is False
            assert "not a valid identifier" in rec.error
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)

    def test_missing_run_function(self):
        """Test validation fails with missing run function."""
        plugin_code = '''
PLUGIN = {
    "name": "test_plugin",
    "description": "Test",
    "parameters": {"type": "OBJECT", "properties": {}},
}
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.test_plugin"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            rec = _validate(module, "test_plugin.py")
            assert rec.valid is False
            assert "Missing callable run" in rec.error
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)


class TestPluginRegistry:
    """Test PluginRegistry class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.logger_messages = []
        self.notify_messages = []

        def logger(msg):
            self.logger_messages.append(msg)

        def notify(msg):
            self.notify_messages.append(msg)

        self.logger = logger
        self.notify = notify

        # Create a simple valid plugin record
        def dummy_run(params, player=None, session_memory=None):
            return "dummy result"

        self.dummy_rec = PluginRecord(
            name="dummy",
            description="Dummy plugin",
            parameters={"type": "OBJECT", "properties": {}},
            run=dummy_run,
            file="dummy.py",
            valid=True,
        )

    def test_registry_creation(self):
        """Test registry creation."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)
        assert registry.has("dummy")
        assert not registry.has("nonexistent")

    def test_get_tool_declarations(self):
        """Test tool declarations generation."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)
        decls = registry.get_tool_declarations()
        assert len(decls) == 1
        assert decls[0]["name"] == "dummy"

    def test_grant_revoke_capability(self):
        """Test granting and revoking capabilities."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        # Grant capability
        result = registry.grant_capability("dummy", "ui.notify")
        assert result is True
        assert "ui.notify" in self.dummy_rec.granted_capabilities

        # Revoke capability
        result = registry.revoke_capability("dummy", "ui.notify")
        assert result is True
        assert "ui.notify" not in self.dummy_rec.granted_capabilities

        # Invalid capability
        result = registry.grant_capability("dummy", "invalid.capability")
        assert result is False

    def test_debug_mode(self):
        """Test debug mode enable/disable."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        registry.enable_debug("dummy")
        assert self.dummy_rec.debug is True

        registry.disable_debug("dummy")
        assert self.dummy_rec.debug is False

    def test_categorization(self):
        """Test category, tags, favorites."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        # Set category
        registry.set_category("dummy", "utility")
        assert self.dummy_rec.category == "utility"

        # Add tag
        registry.add_tag("dummy", "test")
        assert "test" in self.dummy_rec.tags

        # Remove tag
        registry.remove_tag("dummy", "test")
        assert "test" not in self.dummy_rec.tags

        # Toggle favorite
        registry.toggle_favorite("dummy")
        assert self.dummy_rec.favorite is True
        registry.toggle_favorite("dummy")
        assert self.dummy_rec.favorite is False

    def test_priority(self):
        """Test priority ordering."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        registry.set_priority("dummy", 10)
        assert self.dummy_rec.priority == 10

        sorted_plugins = registry.get_sorted_plugins()
        assert sorted_plugins == ["dummy"]

    def test_capability_presets(self):
        """Test capability presets."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        presets = registry.get_capability_presets()
        assert "minimal" in presets
        assert "filesystem" in presets
        assert "network" in presets
        assert "system" in presets
        assert "media" in presets
        assert "data" in presets
        assert "full" in presets

        # Apply preset
        result = registry.apply_capability_preset("dummy", "network")
        assert result is True
        assert "network.http" in self.dummy_rec.granted_capabilities
        assert "network.websocket" in self.dummy_rec.granted_capabilities

        # Invalid preset
        result = registry.apply_capability_preset("dummy", "invalid")
        assert result is False

    def test_version_compatibility(self):
        """Test version compatibility checking."""
        self.dummy_rec.min_jarvis_version = "1.2.0"

        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        # Compatible
        result = registry.check_version_compatibility("dummy", "1.2.0")
        assert result["compatible"] is True

        result = registry.check_version_compatibility("dummy", "1.3.0")
        assert result["compatible"] is True

        # Incompatible
        result = registry.check_version_compatibility("dummy", "1.1.0")
        assert result["compatible"] is False
        assert "Requires Jarvis 1.2.0" in result["reason"]

    def test_performance_metrics(self):
        """Test performance metrics."""
        registry = PluginRegistry({"dummy": self.dummy_rec}, self.logger, self.notify)

        # Simulate some runs
        self.dummy_rec._run_count = 10
        self.dummy_rec._total_run_time = 5.0
        self.dummy_rec._success_count = 8
        self.dummy_rec._failure_count = 2
        self.dummy_rec._last_run_time = 0.5

        perf = registry.get_performance("dummy")
        assert perf["run_count"] == 10
        assert perf["total_time"] == 5.0
        assert perf["avg_time"] == 0.5
        assert perf["success_rate"] == 80.0
        assert perf["success_count"] == 8
        assert perf["failure_count"] == 2


class TestHookSystem:
    """Test global event hooks."""

    def setup_method(self):
        self.logger_messages = []
        self.hook_calls = []

        def logger(msg):
            self.logger_messages.append(msg)

        self.logger = logger

    def test_register_unregister_hook(self):
        """Test hook registration and unregistration."""
        def dummy_run(params, player=None, session_memory=None):
            return "dummy result"

        rec = PluginRecord(
            name="dummy",
            description="Dummy plugin",
            parameters={"type": "OBJECT", "properties": {}},
            run=dummy_run,
            file="dummy.py",
            valid=True,
        )

        registry = PluginRegistry({"dummy": rec}, self.logger)

        def hook_fn(*args, **kwargs):
            self.hook_calls.append(("before_run", args, kwargs))

        # Register hook
        result = registry.register_hook("before_run", hook_fn)
        assert result is True

        # Trigger hook
        registry._trigger_hook("before_run", "dummy", {"param": "value"})
        assert len(self.hook_calls) == 1
        assert self.hook_calls[0][0] == "before_run"

        # Unregister hook
        result = registry.unregister_hook("before_run", hook_fn)
        assert result is True

        # Trigger again - should not call
        registry._trigger_hook("before_run", "dummy", {"param": "value"})
        assert len(self.hook_calls) == 1  # Still 1

    def test_invalid_hook_event(self):
        """Test registering invalid hook event."""
        def dummy_run(params, player=None, session_memory=None):
            return "dummy result"

        rec = PluginRecord(
            name="dummy",
            description="Dummy plugin",
            parameters={"type": "OBJECT", "properties": {}},
            run=dummy_run,
            file="dummy.py",
            valid=True,
        )

        registry = PluginRegistry({"dummy": rec}, self.logger)

        def hook_fn(*args, **kwargs):
            pass

        result = registry.register_hook("invalid_event", hook_fn)
        assert result is False


class TestSecurityScanner:
    """Test plugin security scanner."""

    def test_scan_safe_plugin(self):
        """Test scanning a safe plugin."""
        plugin_code = '''
PLUGIN = {
    "name": "safe_plugin",
    "description": "A safe plugin",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def run(parameters, player=None, session_memory=None):
    return "Safe result"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.safe_plugin"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            def logger(msg):
                pass

            registry = PluginRegistry({}, logger)

            # We need to manually add the plugin to registry for testing
            from core.plugin_loader import _validate
            rec = _validate(module, "safe_plugin.py")
            registry._plugins["safe_plugin"] = rec

            result = registry.scan_plugin_security("safe_plugin")
            assert result["safe"] is True
            assert result["risk_level"] == "safe"
            assert len(result["issues"]) == 0
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)

    def test_scan_dangerous_plugin(self):
        """Test scanning a plugin with dangerous patterns."""
        plugin_code = '''
PLUGIN = {
    "name": "dangerous_plugin",
    "description": "A dangerous plugin",
    "parameters": {"type": "OBJECT", "properties": {}},
}
import subprocess
import os

def run(parameters, player=None, session_memory=None):
    eval("print('hello')")
    os.system("ls")
    subprocess.run(["ls"])
    return "Dangerous result"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.dangerous_plugin"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            def logger(msg):
                pass

            registry = PluginRegistry({}, logger)

            from core.plugin_loader import _validate
            rec = _validate(module, "dangerous_plugin.py")
            registry._plugins["dangerous_plugin"] = rec

            result = registry.scan_plugin_security("dangerous_plugin")
            assert result["safe"] is False
            assert result["risk_level"] == "high"
            assert len(result["issues"]) > 0

            # Check for specific dangerous patterns
            patterns = [i["pattern"] for i in result["issues"]]
            assert "eval" in patterns
            assert "system" in patterns
            assert "subprocess" in patterns
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)


class TestLifecycleHooks:
    """Test plugin lifecycle hooks."""

    def test_lifecycle_hooks_called(self):
        """Test that lifecycle hooks are called."""
        hook_calls = []

        plugin_code = '''
PLUGIN = {
    "name": "lifecycle_test",
    "description": "Test lifecycle hooks",
    "parameters": {"type": "OBJECT", "properties": {}},
}
def on_load():
    hook_calls.append("on_load")

def on_enable():
    hook_calls.append("on_enable")

def on_disable():
    hook_calls.append("on_disable")

def on_unload():
    hook_calls.append("on_unload")

def on_reload():
    hook_calls.append("on_reload")

def run(parameters, player=None, session_memory=None):
    return "Test"
'''

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(plugin_code)
            f.flush()
            path = Path(f.name)

        try:
            import importlib.util
            module_name = "plugins.lifecycle_test"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            module.hook_calls = hook_calls  # Share the list
            spec.loader.exec_module(module)

            def logger(msg):
                pass

            registry = PluginRegistry({}, logger)

            from core.plugin_loader import _validate
            rec = _validate(module, "lifecycle_test.py")
            registry._plugins["lifecycle_test"] = rec

            # Test on_load
            registry._call_lifecycle_hook(rec, "on_load")
            assert "on_load" in hook_calls

            # Test on_enable
            registry._call_lifecycle_hook(rec, "on_enable")
            assert "on_enable" in hook_calls

            # Test on_disable
            registry._call_lifecycle_hook(rec, "on_disable")
            assert "on_disable" in hook_calls

            # Test on_unload
            registry._call_lifecycle_hook(rec, "on_unload")
            assert "on_unload" in hook_calls

            # Test on_reload
            registry._call_lifecycle_hook(rec, "on_reload")
            assert "on_reload" in hook_calls
        finally:
            sys.modules.pop(module_name, None)
            os.unlink(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])