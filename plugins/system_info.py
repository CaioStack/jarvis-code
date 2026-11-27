"""
System Information Plugin — demonstrates Phase 2 plugin features.

This plugin shows system information (CPU, memory, disk) and demonstrates:
- Capability declarations (filesystem.read, network.http)
- Version metadata
- Settings schema for user configuration
"""

import platform
import psutil

PLUGIN = {
    "name": "system_info",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["system", "info", "monitor", "cpu", "memory", "disk"],
    "dependencies": ["psutil"],
    "min_jarvis_version": "1.1.0",
    "description": (
        "Get detailed system information including CPU, memory, disk usage, "
        "and network stats. Trigger with phrases like 'system info', "
        "'how is the computer doing', 'check resources', 'what is my CPU usage'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "detail": {
                "type": "STRING",
                "enum": ["brief", "full", "cpu", "memory", "disk", "network"],
                "description": "Level of detail: brief summary, full report, or specific subsystem",
                "default": "brief"
            },
        },
        "required": [],
    },
    "capabilities": [
        "filesystem.read",   # For reading /proc, /sys on Linux
        "network.http",      # For potential external API calls (e.g., public IP)
    ],
    "sandboxed": False,
    "sandbox_timeout": 30,
    "sandbox_memory_mb": 128,
}

PLUGIN_SETTINGS = {
    "namespace": "system_info",
    "title": "System Info Settings",
    "fields": [
        {
            "key": "show_temperature",
            "label": "Show CPU Temperature",
            "type": "boolean",
            "default": True,
            "description": "Include CPU temperature in full report (Linux only)"
        },
        {
            "key": "include_network",
            "label": "Include Network Stats",
            "type": "boolean",
            "default": True,
            "description": "Show network interface statistics"
        },
        {
            "key": "temperature_unit",
            "label": "Temperature Unit",
            "type": "choice",
            "choices": ["celsius", "fahrenheit"],
            "default": "celsius",
            "description": "Unit for temperature display"
        },
    ],
}

def _get_cpu_temp() -> str:
    """Get CPU temperature if available."""
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return "N/A"
        # Try common sensor names
        for name in ['coretemp', 'cpu_thermal', 'k10temp', 'acpitz']:
            if name in temps:
                for entry in temps[name]:
                    if entry.current:
                        return f"{entry.current:.1f}°C"
        # Fallback: first available
        for sensor_list in temps.values():
            for entry in sensor_list:
                if entry.current:
                    return f"{entry.current:.1f}°C"
    except Exception:
        pass
    return "N/A"

def _format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} PB"

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Get system information."""
    detail = parameters.get("detail", "brief")

    try:
        # Gather system info
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        net = psutil.net_io_counters()

        lines = []

        if detail in ("brief", "full", "cpu"):
            lines.append(f"CPU: {cpu_percent}% used ({cpu_count} cores)")
            if cpu_freq:
                lines.append(f"  Frequency: {cpu_freq.current:.0f} MHz (max {cpu_freq.max:.0f} MHz)")
            temp = _get_cpu_temp()
            if temp != "N/A":
                lines.append(f"  Temperature: {temp}")

        if detail in ("brief", "full", "memory"):
            lines.append(f"Memory: {_format_bytes(mem.used)} / {_format_bytes(mem.total)} ({mem.percent}%)")
            lines.append(f"  Available: {_format_bytes(mem.available)}")

        if detail in ("brief", "full", "disk"):
            lines.append(f"Disk: {_format_bytes(disk.used)} / {_format_bytes(disk.total)} ({disk.percent}%)")
            lines.append(f"  Free: {_format_bytes(disk.free)}")

        if detail in ("full", "network") and net:
            lines.append(f"Network: ↑ {_format_bytes(net.bytes_sent)}  ↓ {_format_bytes(net.bytes_recv)}")
            lines.append(f"  Packets: ↑ {net.packets_sent}  ↓ {net.packets_recv}")
            if net.errin or net.errout:
                lines.append(f"  Errors: in={net.errin} out={net.errout}")

        if detail == "full":
            lines.insert(0, f"System: {platform.system()} {platform.release()} ({platform.machine()})")
            lines.insert(1, f"Hostname: {platform.node()}")
            lines.insert(2, f"Python: {platform.python_version()}")
            lines.insert(3, f"Boot: {psutil.boot_time()}")

        result = "\n".join(lines) if lines else "No information available."

        if player:
            player.write_log(f"JARVIS: System info requested ({detail})")

        return result

    except Exception as e:
        return f"Sir, system info failed: {e}"