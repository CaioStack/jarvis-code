"""
Data Analyzer Plugin — demonstrates data processing, plugin.call capability, and analytics.
"""

PLUGIN = {
    "name": "data_analyzer",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["data", "analysis", "statistics", "csv", "json", "plugin.call"],
    "dependencies": [],
    "min_jarvis_version": "1.2.0",
    "description": (
        "Analyze data from various formats (JSON, CSV, lists). "
        "Trigger with phrases like 'analyze data', 'statistics', 'data summary', "
        "'process csv', 'parse json'. Demonstrates plugin.call capability to use "
        "safe_calc for computations."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "data": {
                "type": "STRING",
                "description": "Data to analyze (JSON array, CSV, or comma-separated values)",
            },
            "format": {
                "type": "STRING",
                "description": "Data format",
                "enum": ["json", "csv", "list"],
                "default": "json",
            },
            "operation": {
                "type": "STRING",
                "description": "Analysis operation",
                "enum": ["stats", "summary", "filter", "aggregate"],
                "default": "stats",
            },
            "filter_expr": {
                "type": "STRING",
                "description": "Filter expression (for filter operation)",
                "default": "",
            },
        },
        "required": ["data"],
    },
    "capabilities": ["plugin.call"],
    "sandboxed": False,
    "debug": True,
}

# Settings schema for UI configuration
PLUGIN_SETTINGS = {
    "namespace": "data_analyzer",
    "title": "Data Analyzer Configuration",
    "fields": [
        {
            "key": "default_format",
            "label": "Default Data Format",
            "type": "choice",
            "choices": ["json", "csv", "list"],
            "default": "json",
        },
        {
            "key": "max_rows",
            "label": "Max Rows to Process",
            "type": "integer",
            "default": 10000,
            "min": 100,
            "max": 100000,
        },
        {
            "key": "use_safe_calc",
            "label": "Use Safe Calc for Computations",
            "type": "boolean",
            "default": True,
        },
    ],
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Analyze data."""
    data_str = parameters.get("data", "")
    format_type = parameters.get("format", "json")
    operation = parameters.get("operation", "stats")
    filter_expr = parameters.get("filter_expr", "")

    if not data_str:
        return "Please provide data to analyze."

    # Parse data based on format
    try:
        if format_type == "json":
            import json
            data = json.loads(data_str)
            if not isinstance(data, list):
                return "JSON data must be an array."
        elif format_type == "csv":
            import csv
            import io
            reader = csv.DictReader(io.StringIO(data_str))
            data = list(reader)
        elif format_type == "list":
            data = [x.strip() for x in data_str.split(',')]
        else:
            return f"Unknown format: {format_type}"
    except Exception as e:
        return f"Failed to parse data: {e}"

    if not data:
        return "No data to analyze."

    # Limit rows
    max_rows = 10000
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("data_analyzer")
        max_rows = config.get("max_rows", 10000)
        use_safe_calc = config.get("use_safe_calc", True)
    except Exception:
        use_safe_calc = True

    if len(data) > max_rows:
        data = data[:max_rows]

    if operation == "stats":
        return analyze_stats(data, use_safe_calc, player, session_memory)
    elif operation == "summary":
        return analyze_summary(data)
    elif operation == "filter":
        return filter_data(data, filter_expr)
    elif operation == "aggregate":
        return aggregate_data(data)
    else:
        return f"Unknown operation: {operation}"


def analyze_stats(data, use_safe_calc, player, session_memory):
    """Calculate statistics on numeric data."""
    # Extract numeric values
    numeric_values = []
    for item in data:
        if isinstance(item, (int, float)):
            numeric_values.append(item)
        elif isinstance(item, dict):
            for v in item.values():
                if isinstance(v, (int, float)):
                    numeric_values.append(v)
        elif isinstance(item, list):
            for v in item:
                if isinstance(v, (int, float)):
                    numeric_values.append(v)

    if not numeric_values:
        return "No numeric values found in data."

    if use_safe_calc and player and hasattr(player, 'plugin_registry'):
        # Use safe_calc plugin for computations
        registry = player.plugin_registry
        try:
            # Calculate mean
            mean_expr = f"sum({numeric_values}) / {len(numeric_values)}"
            mean_result = registry.call_plugin("data_analyzer", "safe_calc", {"expression": mean_expr}, player, session_memory)

            # Calculate std dev
            import math
            mean_val = sum(numeric_values) / len(numeric_values)
            variance = sum((x - mean_val) ** 2 for x in numeric_values) / len(numeric_values)
            std_expr = f"sqrt({variance})"
            std_result = registry.call_plugin("data_analyzer", "safe_calc", {"expression": std_expr}, player, session_memory)

            # Min/max
            min_expr = f"min({numeric_values})"
            max_expr = f"max({numeric_values})"
            min_result = registry.call_plugin("data_analyzer", "safe_calc", {"expression": min_expr}, player, session_memory)
            max_result = registry.call_plugin("data_analyzer", "safe_calc", {"expression": max_expr}, player, session_memory)

            return (f"Statistics (via safe_calc):\n"
                    f"  Count: {len(numeric_values)}\n"
                    f"  Mean: {mean_result}\n"
                    f"  Std Dev: {std_result}\n"
                    f"  Min: {min_result}\n"
                    f"  Max: {max_result}\n"
                    f"  Sum: {sum(numeric_values)}")
        except Exception as e:
            # Fall back to local calculation
            pass

    # Local calculation fallback
    import math
    mean_val = sum(numeric_values) / len(numeric_values)
    variance = sum((x - mean_val) ** 2 for x in numeric_values) / len(numeric_values)
    std_dev = math.sqrt(variance)

    return (f"Statistics:\n"
            f"  Count: {len(numeric_values)}\n"
            f"  Mean: {mean_val:.4f}\n"
            f"  Std Dev: {std_dev:.4f}\n"
            f"  Min: {min(numeric_values)}\n"
            f"  Max: {max(numeric_values)}\n"
            f"  Sum: {sum(numeric_values)}")


def analyze_summary(data):
    """Provide a summary of the data structure."""
    if isinstance(data[0], dict):
        keys = set()
        for item in data:
            keys.update(item.keys())
        return (f"Data Summary:\n"
                f"  Rows: {len(data)}\n"
                f"  Columns: {len(keys)}\n"
                f"  Fields: {', '.join(sorted(keys))}\n"
                f"  Sample: {data[0]}")
    elif isinstance(data[0], list):
        return (f"Data Summary:\n"
                f"  Rows: {len(data)}\n"
                f"  Columns per row: {len(data[0]) if data else 0}\n"
                f"  Sample: {data[0]}")
    else:
        return (f"Data Summary:\n"
                f"  Items: {len(data)}\n"
                f"  Type: {type(data[0]).__name__}\n"
                f"  Sample: {data[:5]}")


def filter_data(data, filter_expr):
    """Filter data based on expression."""
    if not filter_expr:
        return "Please provide a filter expression."

    # Simple filter: field=value or field>value etc.
    import re
    match = re.match(r'(\w+)\s*([=<>!]+)\s*(.+)', filter_expr)
    if not match:
        return f"Invalid filter expression: {filter_expr}"

    field, operator, value = match.groups()

    # Try to convert value to appropriate type
    try:
        value = float(value)
        if value == int(value):
            value = int(value)
    except ValueError:
        pass  # Keep as string

    filtered = []
    for item in data:
        if isinstance(item, dict) and field in item:
            item_val = item[field]
            if operator == '=' and item_val == value:
                filtered.append(item)
            elif operator == '!=' and item_val != value:
                filtered.append(item)
            elif operator == '>' and item_val > value:
                filtered.append(item)
            elif operator == '<' and item_val < value:
                filtered.append(item)
            elif operator == '>=' and item_val >= value:
                filtered.append(item)
            elif operator == '<=' and item_val <= value:
                filtered.append(item)

    return f"Filtered {len(filtered)} of {len(data)} rows:\n" + str(filtered[:10])


def aggregate_data(data):
    """Aggregate data by a field."""
    if not data or not isinstance(data[0], dict):
        return "Aggregation requires list of objects."

    # Group by first field
    first_key = list(data[0].keys())[0]
    groups = {}
    for item in data:
        key = item.get(first_key, 'unknown')
        if key not in groups:
            groups[key] = []
        groups[key].append(item)

    result = f"Aggregation by '{first_key}':\n"
    for key, items in list(groups.items())[:10]:
        result += f"  {key}: {len(items)} items\n"

    if len(groups) > 10:
        result += f"  ... and {len(groups) - 10} more groups"

    return result


def on_load():
    print("[SYS] [PluginLoader] data_analyzer: on_load hook called")


def on_enable():
    print("[SYS] [PluginLoader] data_analyzer: on_enable hook called")


def on_disable():
    print("[SYS] [PluginLoader] data_analyzer: on_disable hook called")


def on_unload():
    print("[SYS] [PluginLoader] data_analyzer: on_unload hook called")


def on_reload():
    print("[SYS] [PluginLoader] data_analyzer: on_reload hook called")