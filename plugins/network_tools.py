"""
Network Tools Plugin — demonstrates network capabilities and HTTP requests.
"""

PLUGIN = {
    "name": "network_tools",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["network", "http", "api", "web", "requests"],
    "dependencies": ["requests"],
    "min_jarvis_version": "1.2.0",
    "description": (
        "Perform HTTP requests and network operations. "
        "Trigger with phrases like 'fetch url', 'get webpage', 'http request', "
        "'check website', 'download file'. Requires network.http capability."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "url": {
                "type": "STRING",
                "description": "URL to fetch",
            },
            "method": {
                "type": "STRING",
                "description": "HTTP method (GET, POST, PUT, DELETE)",
                "enum": ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
                "default": "GET",
            },
            "headers": {
                "type": "STRING",
                "description": "JSON string of headers to send",
                "default": "{}",
            },
            "data": {
                "type": "STRING",
                "description": "JSON string of request body data",
                "default": "{}",
            },
            "timeout": {
                "type": "INTEGER",
                "description": "Request timeout in seconds",
                "default": 30,
            },
        },
        "required": ["url"],
    },
    "capabilities": ["network.http"],
    "sandboxed": False,
}

# Settings schema for UI configuration
PLUGIN_SETTINGS = {
    "namespace": "network_tools",
    "title": "Network Tools Configuration",
    "fields": [
        {
            "key": "default_timeout",
            "label": "Default Timeout (seconds)",
            "type": "integer",
            "default": 30,
            "min": 5,
            "max": 300,
        },
        {
            "key": "max_redirects",
            "label": "Max Redirects",
            "type": "integer",
            "default": 10,
            "min": 0,
            "max": 50,
        },
        {
            "key": "verify_ssl",
            "label": "Verify SSL Certificates",
            "type": "boolean",
            "default": True,
        },
        {
            "key": "user_agent",
            "label": "Custom User-Agent",
            "type": "string",
            "default": "Jarvis-Code/1.0",
        },
    ],
    "action": {
        "label": "Test Connection",
        "method": "test_connection",
    },
}

import requests
import json


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Perform an HTTP request."""
    url = parameters.get("url", "").strip()
    method = parameters.get("method", "GET").upper()
    headers_str = parameters.get("headers", "{}")
    data_str = parameters.get("data", "{}")
    timeout = parameters.get("timeout", 30)

    if not url:
        return "Please provide a URL to fetch."

    # Load settings
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("network_tools")
        default_timeout = config.get("default_timeout", 30)
        max_redirects = config.get("max_redirects", 10)
        verify_ssl = config.get("verify_ssl", True)
        user_agent = config.get("user_agent", "Jarvis-Code/1.0")
    except Exception:
        default_timeout = 30
        max_redirects = 10
        verify_ssl = True
        user_agent = "Jarvis-Code/1.0"

    if timeout > 0:
        default_timeout = timeout

    try:
        headers = json.loads(headers_str) if headers_str else {}
        headers.setdefault("User-Agent", user_agent)

        data = json.loads(data_str) if data_str else {}

        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=data if data else None,
            timeout=default_timeout,
            allow_redirects=True,
            verify=verify_ssl,
        )

        # Format response
        result = f"HTTP {response.status_code} {response.reason}\n"
        result += f"URL: {response.url}\n"
        result += f"Headers: {dict(response.headers)}\n"

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                result += f"JSON: {json.dumps(response.json(), indent=2)[:2000]}"
            except Exception:
                result += f"Body: {response.text[:2000]}"
        else:
            result += f"Body: {response.text[:2000]}"

        if player:
            player.write_log(f"JARVIS: HTTP {method} {url} -> {response.status_code}")

        return result

    except requests.exceptions.Timeout:
        return f"Request timed out after {default_timeout} seconds."
    except requests.exceptions.ConnectionError as e:
        return f"Connection error: {e}"
    except requests.exceptions.TooManyRedirects:
        return f"Too many redirects (max {max_redirects})."
    except requests.exceptions.RequestException as e:
        return f"Request failed: {e}"
    except json.JSONDecodeError as e:
        return f"Invalid JSON in headers or data: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


def test_connection() -> str:
    """Test the network connection with a simple request."""
    try:
        import requests
        response = requests.get("https://httpbin.org/get", timeout=10)
        if response.status_code == 200:
            return "Network connection test successful!"
        else:
            return f"Test failed with status {response.status_code}"
    except Exception as e:
        return f"Connection test failed: {e}"


def on_load():
    """Called when plugin is first loaded."""
    print("[SYS] [PluginLoader] network_tools: on_load hook called")


def on_enable():
    """Called when plugin is enabled."""
    print("[SYS] [PluginLoader] network_tools: on_enable hook called")


def on_disable():
    """Called when plugin is disabled."""
    print("[SYS] [PluginLoader] network_tools: on_disable hook called")


def on_unload():
    """Called when plugin is unloaded."""
    print("[SYS] [PluginLoader] network_tools: on_unload hook called")


def on_reload():
    """Called when plugin is hot-reloaded."""
    print("[SYS] [PluginLoader] network_tools: on_reload hook called")