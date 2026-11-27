"""
Weather Service Plugin — demonstrates cost tracking, i18n, health checks, and webhooks.
"""

PLUGIN = {
    "name": "weather_service",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["weather", "api", "cost", "i18n", "webhook", "health"],
    "dependencies": ["requests"],
    "min_jarvis_version": "1.2.0",
    "description": (
        "Fetch weather data from OpenWeatherMap API. "
        "Trigger with phrases like 'weather', 'forecast', 'temperature', 'climate'. "
        "Demonstrates cost tracking (API calls), i18n translations, health checks, and webhooks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "location": {
                "type": "STRING",
                "description": "City name or 'lat,lon' coordinates",
            },
            "units": {
                "type": "STRING",
                "description": "Units system",
                "enum": ["metric", "imperial", "standard"],
                "default": "metric",
            },
            "forecast_days": {
                "type": "INTEGER",
                "description": "Number of forecast days (1-5)",
                "default": 1,
                "minimum": 1,
                "maximum": 5,
            },
        },
        "required": ["location"],
    },
    "capabilities": ["network.http", "config.read"],
    "sandboxed": False,
    "category": "utility",
    "tags": ["weather", "api", "external"],
}

# Translations for i18n support
TRANSLATIONS = {
    "en": {
        "description": "Fetch weather data from OpenWeatherMap API",
        "help": "Use 'weather in London' or 'forecast for Tokyo' to get weather info",
        "error_no_api_key": "OpenWeatherMap API key not configured. Please set it in plugin settings.",
        "error_not_found": "Location not found. Please check the city name.",
        "error_api": "Weather API error: {error}",
    },
    "pt": {
        "description": "Obter dados meteorológicos da API OpenWeatherMap",
        "help": "Use 'clima em São Paulo' ou 'previsão para Tóquio' para obter informações do tempo",
        "error_no_api_key": "Chave da API OpenWeatherMap não configurada. Configure nas configurações do plugin.",
        "error_not_found": "Local não encontrado. Verifique o nome da cidade.",
        "error_api": "Erro na API do tempo: {error}",
    },
    "es": {
        "description": "Obtener datos meteorológicos de la API OpenWeatherMap",
        "help": "Use 'clima en Madrid' o 'pronóstico para Tokio' para obtener información del tiempo",
        "error_no_api_key": "Clave de API OpenWeatherMap no configurada. Configúrela en la configuración del plugin.",
        "error_not_found": "Ubicación no encontrada. Verifique el nombre de la ciudad.",
        "error_api": "Error de la API del clima: {error}",
    },
}

# Settings schema for UI configuration
PLUGIN_SETTINGS = {
    "namespace": "weather_service",
    "title": "Weather Service Configuration",
    "fields": [
        {
            "key": "api_key",
            "label": "OpenWeatherMap API Key",
            "type": "secret",
            "default": "",
            "required": True,
        },
        {
            "key": "default_units",
            "label": "Default Units",
            "type": "choice",
            "choices": ["metric", "imperial", "standard"],
            "default": "metric",
        },
        {
            "key": "default_forecast_days",
            "label": "Default Forecast Days",
            "type": "integer",
            "default": 1,
            "min": 1,
            "max": 5,
        },
        {
            "key": "cost_per_call_usd",
            "label": "Cost per API Call (USD)",
            "type": "number",
            "default": 0.0001,
            "min": 0,
        },
        {
            "key": "webhook_url",
            "label": "Webhook URL for Weather Alerts",
            "type": "string",
            "default": "",
        },
        {
            "key": "webhook_secret",
            "label": "Webhook Secret (HMAC)",
            "type": "secret",
            "default": "",
        },
    ],
    "action": {
        "label": "Test API Connection",
        "method": "test_connection",
    },
}

# Changelog for version tracking
CHANGELOG = [
    {
        "version": "1.0.0",
        "date": "2024-01-15",
        "changes": "Initial release with current weather and forecast support",
    },
]

import requests
import json


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Fetch weather data."""
    location = parameters.get("location", "").strip()
    units = parameters.get("units", "metric")
    forecast_days = parameters.get("forecast_days", 1)

    if not location:
        return get_translation("error_no_location", player)

    # Load settings
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("weather_service")
        api_key = config.get("api_key", "")
        default_units = config.get("default_units", "metric")
        cost_per_call = config.get("cost_per_call_usd", 0.0001)
        webhook_url = config.get("webhook_url", "")
        webhook_secret = config.get("webhook_secret", "")
    except Exception:
        api_key = ""
        default_units = "metric"
        cost_per_call = 0.0001
        webhook_url = ""
        webhook_secret = ""

    if not api_key:
        return get_translation("error_no_api_key", player)

    if units == "default":
        units = default_units

    try:
        # Get current weather
        current_url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "appid": api_key,
            "units": units,
        }
        response = requests.get(current_url, params=params, timeout=10)

        # Record API cost
        if player and hasattr(player, 'plugin_registry'):
            registry = player.plugin_registry
            registry.record_plugin_cost("weather_service", cost_per_call, "USD", {
                "model": "openweathermap",
                "endpoint": "current_weather",
                "location": location,
            })

        if response.status_code == 404:
            return get_translation("error_not_found", player)
        elif response.status_code != 200:
            return get_translation("error_api", player).format(error=response.text[:200])

        current_data = response.json()

        # Get forecast if requested
        forecast_data = None
        if forecast_days > 1:
            forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
            forecast_response = requests.get(forecast_url, params=params, timeout=10)
            if forecast_response.status_code == 200:
                forecast_data = forecast_response.json()
                # Record cost for forecast call too
                if player and hasattr(player, 'plugin_registry'):
                    registry = player.plugin_registry
                    registry.record_plugin_cost("weather_service", cost_per_call, "USD", {
                        "model": "openweathermap",
                        "endpoint": "forecast",
                        "location": location,
                    })

        # Format response
        temp_unit = "°C" if units == "metric" else "°F" if units == "imperial" else "K"
        wind_unit = "m/s" if units == "metric" else "mph"

        result = f"Weather for {current_data['name']}, {current_data['sys']['country']}:\n"
        result += f"  Temperature: {current_data['main']['temp']}{temp_unit}\n"
        result += f"  Feels like: {current_data['main']['feels_like']}{temp_unit}\n"
        result += f"  Humidity: {current_data['main']['humidity']}%\n"
        result += f"  Pressure: {current_data['main']['pressure']} hPa\n"
        result += f"  Wind: {current_data['wind']['speed']} {wind_unit}\n"
        result += f"  Conditions: {current_data['weather'][0]['description'].capitalize()}\n"

        if forecast_data:
            result += f"\n{forecast_days}-Day Forecast:\n"
            # Group by day
            from collections import defaultdict
            daily = defaultdict(list)
            for item in forecast_data['list'][:forecast_days * 8]:
                from datetime import datetime
                dt = datetime.fromtimestamp(item['dt'])
                day_key = dt.strftime("%Y-%m-%d")
                daily[day_key].append(item)

            for day, items in list(daily.items())[:forecast_days]:
                temps = [i['main']['temp'] for i in items]
                conditions = [i['weather'][0]['description'] for i in items]
                result += f"  {day}: {min(temps):.1f}-{max(temps):.1f}{temp_unit}, {max(set(conditions), key=conditions.count).capitalize()}\n"

        # Trigger webhook if configured
        if webhook_url and player and hasattr(player, 'plugin_registry'):
            registry = player.plugin_registry
            registry._trigger_webhooks("weather_service", "plugin_run", {
                "plugin": "weather_service",
                "location": location,
                "temperature": current_data['main']['temp'],
                "conditions": current_data['weather'][0]['description'],
            })

        if player:
            player.write_log(f"JARVIS: Weather for {location} - {current_data['main']['temp']}{temp_unit}")

        return result

    except requests.exceptions.Timeout:
        return get_translation("error_timeout", player)
    except requests.exceptions.RequestException as e:
        return get_translation("error_api", player).format(error=str(e))
    except Exception as e:
        return f"Unexpected error: {e}"


def get_translation(key: str, player=None) -> str:
    """Get translation for current locale."""
    locale = "en"
    try:
        if player and hasattr(player, 'plugin_registry'):
            registry = player.plugin_registry
            locale = registry.get_plugin_locale("weather_service")
    except Exception:
        pass

    translations = TRANSLATIONS.get(locale, TRANSLATIONS["en"])
    return translations.get(key, TRANSLATIONS["en"].get(key, key))


def test_connection() -> str:
    """Test the API connection."""
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("weather_service")
        api_key = config.get("api_key", "")

        if not api_key:
            return "API key not configured"

        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": "London", "appid": api_key, "units": "metric"},
            timeout=10,
        )

        if response.status_code == 200:
            return "API connection successful!"
        elif response.status_code == 401:
            return "Invalid API key"
        else:
            return f"API error: {response.status_code}"
    except Exception as e:
        return f"Connection test failed: {e}"


def on_load():
    print("[SYS] [PluginLoader] weather_service: on_load hook called")


def on_enable():
    print("[SYS] [PluginLoader] weather_service: on_enable hook called")
    # Register webhook when enabled
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("weather_service")
        webhook_url = config.get("webhook_url", "")
        webhook_secret = config.get("webhook_secret", "")
        if webhook_url:
            # This would be done by the registry in real usage
            pass
    except Exception:
        pass


def on_disable():
    print("[SYS] [PluginLoader] weather_service: on_disable hook called")


def on_unload():
    print("[SYS] [PluginLoader] weather_service: on_unload hook called")


def on_reload():
    print("[SYS] [PluginLoader] weather_service: on_reload hook called")


# Migration function example
def migrate_v1_to_v2(config):
    """Migrate config from v1 to v2."""
    # Add new fields with defaults
    config.setdefault("cost_per_call_usd", 0.0001)
    config.setdefault("webhook_url", "")
    config.setdefault("webhook_secret", "")
    return config