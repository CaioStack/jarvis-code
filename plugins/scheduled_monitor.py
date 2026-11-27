"""
Scheduled Monitor Plugin — demonstrates plugin scheduling, metrics streaming, and health checks.
"""

PLUGIN = {
    "name": "scheduled_monitor",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["monitor", "scheduling", "metrics", "health", "system", "cron"],
    "dependencies": ["psutil"],
    "min_jarvis_version": "1.2.0",
    "description": (
        "Monitor system resources on a schedule. "
        "Trigger with phrases like 'system monitor', 'check resources', 'system health', "
        "'scheduled check'. Demonstrates plugin scheduling (cron), metrics streaming, "
        "and comprehensive health checks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "check_type": {
                "type": "STRING",
                "description": "Type of check to perform",
                "enum": ["cpu", "memory", "disk", "network", "all"],
                "default": "all",
            },
            "threshold_cpu": {
                "type": "INTEGER",
                "description": "CPU usage alert threshold (%)",
                "default": 80,
            },
            "threshold_memory": {
                "type": "INTEGER",
                "description": "Memory usage alert threshold (%)",
                "default": 85,
            },
            "threshold_disk": {
                "type": "INTEGER",
                "description": "Disk usage alert threshold (%)",
                "default": 90,
            },
        },
        "required": [],
    },
    "capabilities": ["system.monitor", "config.read", "ui.notify"],
    "sandboxed": False,
    "category": "system",
    "tags": ["monitoring", "scheduling", "health", "metrics"],
}

# Settings schema for UI configuration
PLUGIN_SETTINGS = {
    "namespace": "scheduled_monitor",
    "title": "Scheduled Monitor Configuration",
    "fields": [
        {
            "key": "default_check_type",
            "label": "Default Check Type",
            "type": "choice",
            "choices": ["cpu", "memory", "disk", "network", "all"],
            "default": "all",
        },
        {
            "key": "alert_cpu_threshold",
            "label": "CPU Alert Threshold (%)",
            "type": "integer",
            "default": 80,
            "min": 50,
            "max": 100,
        },
        {
            "key": "alert_memory_threshold",
            "label": "Memory Alert Threshold (%)",
            "type": "integer",
            "default": 85,
            "min": 50,
            "max": 100,
        },
        {
            "key": "alert_disk_threshold",
            "label": "Disk Alert Threshold (%)",
            "type": "integer",
            "default": 90,
            "min": 50,
            "max": 100,
        },
        {
            "key": "enable_notifications",
            "label": "Enable Alert Notifications",
            "type": "boolean",
            "default": True,
        },
        {
            "key": "metrics_stream_interval",
            "label": "Metrics Stream Interval (seconds)",
            "type": "integer",
            "default": 30,
            "min": 5,
            "max": 300,
        },
    ],
    "action": {
        "label": "Run Health Check Now",
        "method": "run_health_check_now",
    },
}

import psutil
import time


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Perform system monitoring check."""
    check_type = parameters.get("check_type", "all")
    cpu_threshold = parameters.get("threshold_cpu", 80)
    mem_threshold = parameters.get("threshold_memory", 85)
    disk_threshold = parameters.get("threshold_disk", 90)

    # Load settings
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("scheduled_monitor")
        cpu_threshold = config.get("alert_cpu_threshold", cpu_threshold)
        mem_threshold = config.get("alert_memory_threshold", mem_threshold)
        disk_threshold = config.get("alert_disk_threshold", disk_threshold)
        enable_notifications = config.get("enable_notifications", True)
    except Exception:
        enable_notifications = True

    results = []
    alerts = []

    if check_type in ("cpu", "all"):
        cpu_data = check_cpu(cpu_threshold)
        results.append(cpu_data)
        if cpu_data.get("alert"):
            alerts.append(cpu_data["alert"])

    if check_type in ("memory", "all"):
        mem_data = check_memory(mem_threshold)
        results.append(mem_data)
        if mem_data.get("alert"):
            alerts.append(mem_data["alert"])

    if check_type in ("disk", "all"):
        disk_data = check_disk(disk_threshold)
        results.append(disk_data)
        if disk_data.get("alert"):
            alerts.append(disk_data["alert"])

    if check_type in ("network", "all"):
        net_data = check_network()
        results.append(net_data)

    # Format output
    output = "System Monitor Report\n"
    output += "=" * 40 + "\n"

    for result in results:
        output += f"\n{result['title']}:\n"
        for key, value in result.items():
            if key not in ("title", "alert"):
                output += f"  {key}: {value}\n"
        if result.get("alert"):
            output += f"  ⚠️ ALERT: {result['alert']}\n"

    if alerts:
        output += f"\n⚠️ {len(alerts)} ALERT(S) TRIGGERED\n"
        if enable_notifications and player:
            for alert in alerts:
                player.write_log(f"JARVIS ALERT: {alert}")
    else:
        output += "\n✅ All systems normal"

    return output


def check_cpu(threshold):
    """Check CPU usage."""
    cpu_percent = psutil.cpu_percent(interval=1)
    cpu_count = psutil.cpu_count()
    cpu_freq = psutil.cpu_freq()

    result = {
        "title": "CPU",
        "usage_percent": f"{cpu_percent:.1f}%",
        "cores": cpu_count,
        "frequency": f"{cpu_freq.current:.0f} MHz" if cpu_freq else "N/A",
    }

    if cpu_percent > threshold:
        result["alert"] = f"CPU usage {cpu_percent:.1f}% exceeds threshold {threshold}%"

    return result


def check_memory(threshold):
    """Check memory usage."""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    result = {
        "title": "Memory",
        "usage_percent": f"{mem.percent:.1f}%",
        "total": f"{mem.total / (1024**3):.1f} GB",
        "available": f"{mem.available / (1024**3):.1f} GB",
        "used": f"{mem.used / (1024**3):.1f} GB",
        "swap_usage": f"{swap.percent:.1f}%",
    }

    if mem.percent > threshold:
        result["alert"] = f"Memory usage {mem.percent:.1f}% exceeds threshold {threshold}%"

    return result


def check_disk(threshold):
    """Check disk usage."""
    partitions = psutil.disk_partitions()
    alerts = []
    worst_usage = 0
    worst_path = ""

    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            if usage.percent > worst_usage:
                worst_usage = usage.percent
                worst_path = partition.mountpoint
            if usage.percent > threshold:
                alerts.append(f"Disk {partition.mountpoint} at {usage.percent:.1f}%")
        except PermissionError:
            continue

    result = {
        "title": "Disk",
        "partitions_checked": len(partitions),
        "worst_usage": f"{worst_usage:.1f}%",
        "worst_path": worst_path,
    }

    if alerts:
        result["alert"] = "; ".join(alerts)

    return result


def check_network():
    """Check network interfaces."""
    net_io = psutil.net_io_counters()
    net_if = psutil.net_if_addrs()

    result = {
        "title": "Network",
        "bytes_sent": f"{net_io.bytes_sent / (1024**2):.1f} MB",
        "bytes_recv": f"{net_io.bytes_recv / (1024**2):.1f} MB",
        "packets_sent": net_io.packets_sent,
        "packets_recv": net_io.packets_recv,
        "interfaces": len(net_if),
    }

    return result


def run_health_check_now() -> str:
    """Run a comprehensive health check."""
    # This would be called via the action button in UI
    health_results = {
        "cpu": check_cpu(80),
        "memory": check_memory(85),
        "disk": check_disk(90),
        "network": check_network(),
    }

    output = "Comprehensive Health Check\n"
    output += "=" * 40 + "\n"

    issues = 0
    for name, result in health_results.items():
        output += f"\n{result['title']}: "
        if result.get("alert"):
            output += f"⚠️ {result['alert']}\n"
            issues += 1
        else:
            output += "✅ OK\n"

    output += f"\n{'✅ All systems healthy' if issues == 0 else f'⚠️ {issues} issue(s) found'}"

    return output


def on_load():
    print("[SYS] [PluginLoader] scheduled_monitor: on_load hook called")


def on_enable():
    print("[SYS] [PluginLoader] scheduled_monitor: on_enable hook called")
    # Start metrics streaming when enabled
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("scheduled_monitor")
        interval = config.get("metrics_stream_interval", 30)
        # In real usage, the registry would start the stream
        print(f"[SYS] [PluginLoader] scheduled_monitor: metrics stream interval = {interval}s")
    except Exception:
        pass


def on_disable():
    print("[SYS] [PluginLoader] scheduled_monitor: on_disable hook called")
    # Stop metrics streaming when disabled


def on_unload():
    print("[SYS] [PluginLoader] scheduled_monitor: on_unload hook called")


def on_reload():
    print("[SYS] [PluginLoader] scheduled_monitor: on_reload hook called")