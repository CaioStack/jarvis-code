"""
Smart Recommendations Plugin — demonstrates A/B testing, ACLs, and analytics.
"""

PLUGIN = {
    "name": "smart_recommendations",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["recommendations", "ml", "ab-testing", "acl", "analytics", "personalization"],
    "dependencies": [],
    "min_jarvis_version": "1.2.0",
    "description": (
        "Provide personalized recommendations using collaborative filtering. "
        "Trigger with phrases like 'recommend', 'suggest', 'what should I watch', "
        "'movie recommendations', 'book suggestions'. Demonstrates A/B testing, "
        "access control lists (ACLs), and usage analytics."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "category": {
                "type": "STRING",
                "description": "Recommendation category",
                "enum": ["movies", "books", "music", "games", "restaurants", "general"],
                "default": "general",
            },
            "user_preferences": {
                "type": "STRING",
                "description": "JSON string of user preferences",
                "default": "{}",
            },
            "count": {
                "type": "INTEGER",
                "description": "Number of recommendations",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": [],
    },
    "capabilities": ["memory.read", "memory.write", "config.read"],
    "sandboxed": False,
    "category": "ai",
    "tags": ["recommendations", "personalization", "ml"],
    # ACL: Only allow premium users during certain hours
    # This would be set via set_plugin_acl()
}

# Settings schema for UI configuration
PLUGIN_SETTINGS = {
    "namespace": "smart_recommendations",
    "title": "Smart Recommendations Configuration",
    "fields": [
        {
            "key": "algorithm",
            "label": "Recommendation Algorithm",
            "type": "choice",
            "choices": ["collaborative", "content_based", "hybrid", "popularity"],
            "default": "hybrid",
        },
        {
            "key": "min_confidence",
            "label": "Minimum Confidence Score",
            "type": "number",
            "default": 0.3,
            "min": 0,
            "max": 1,
        },
        {
            "key": "enable_ab_testing",
            "label": "Enable A/B Testing",
            "type": "boolean",
            "default": True,
        },
        {
            "key": "ab_traffic_split",
            "label": "A/B Traffic Split (Variant A %)",
            "type": "number",
            "default": 0.5,
            "min": 0,
            "max": 1,
        },
        {
            "key": "premium_only",
            "label": "Premium Users Only",
            "type": "boolean",
            "default": False,
        },
    ],
}

# Sample data for demonstration
SAMPLE_ITEMS = {
    "movies": [
        {"id": 1, "title": "The Matrix", "genre": "Sci-Fi", "year": 1999, "rating": 8.7},
        {"id": 2, "title": "Inception", "genre": "Sci-Fi", "year": 2010, "rating": 8.8},
        {"id": 3, "title": "Interstellar", "genre": "Sci-Fi", "year": 2014, "rating": 8.6},
        {"id": 4, "title": "The Dark Knight", "genre": "Action", "year": 2008, "rating": 9.0},
        {"id": 5, "title": "Pulp Fiction", "genre": "Crime", "year": 1994, "rating": 8.9},
        {"id": 6, "title": "Forrest Gump", "genre": "Drama", "year": 1994, "rating": 8.8},
        {"id": 7, "title": "Fight Club", "genre": "Drama", "year": 1999, "rating": 8.8},
        {"id": 8, "title": "The Shawshank Redemption", "genre": "Drama", "year": 1994, "rating": 9.3},
    ],
    "books": [
        {"id": 1, "title": "1984", "author": "George Orwell", "genre": "Dystopian", "year": 1949, "rating": 4.7},
        {"id": 2, "title": "To Kill a Mockingbird", "author": "Harper Lee", "genre": "Fiction", "year": 1960, "rating": 4.8},
        {"id": 3, "title": "The Great Gatsby", "author": "F. Scott Fitzgerald", "genre": "Fiction", "year": 1925, "rating": 4.4},
        {"id": 4, "title": "Dune", "author": "Frank Herbert", "genre": "Sci-Fi", "year": 1965, "rating": 4.6},
        {"id": 5, "title": "Sapiens", "author": "Yuval Noah Harari", "genre": "Non-Fiction", "year": 2011, "rating": 4.6},
    ],
    "music": [
        {"id": 1, "title": "Bohemian Rhapsody", "artist": "Queen", "genre": "Rock", "year": 1975},
        {"id": 2, "title": "Stairway to Heaven", "artist": "Led Zeppelin", "genre": "Rock", "year": 1971},
        {"id": 3, "title": "Imagine", "artist": "John Lennon", "genre": "Pop", "year": 1971},
        {"id": 4, "title": "Billie Jean", "artist": "Michael Jackson", "genre": "Pop", "year": 1982},
        {"id": 5, "title": "Hotel California", "artist": "Eagles", "genre": "Rock", "year": 1976},
    ],
    "games": [
        {"id": 1, "title": "The Witcher 3", "genre": "RPG", "year": 2015, "rating": 9.3},
        {"id": 2, "title": "Elden Ring", "genre": "Action RPG", "year": 2022, "rating": 9.6},
        {"id": 3, "title": "Red Dead Redemption 2", "genre": "Action Adventure", "year": 2018, "rating": 9.7},
        {"id": 4, "title": "God of War", "genre": "Action Adventure", "year": 2018, "rating": 9.4},
        {"id": 5, "title": "Cyberpunk 2077", "genre": "RPG", "year": 2020, "rating": 8.6},
    ],
    "restaurants": [
        {"id": 1, "name": "Le Bernardin", "cuisine": "French", "rating": 4.9, "price": "$$$$"},
        {"id": 2, "name": "Noma", "cuisine": "Nordic", "rating": 4.8, "price": "$$$$"},
        {"id": 3, "name": "Osteria Francescana", "cuisine": "Italian", "rating": 4.9, "price": "$$$$"},
        {"id": 4, "name": "Eleven Madison Park", "cuisine": "American", "rating": 4.8, "price": "$$$$"},
        {"id": 5, "name": "Gaggan", "cuisine": "Indian", "rating": 4.7, "price": "$$$"},
    ],
}

import json
import random


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Generate personalized recommendations."""
    category = parameters.get("category", "general")
    prefs_str = parameters.get("user_preferences", "{}")
    count = parameters.get("count", 5)

    # Parse user preferences
    try:
        user_prefs = json.loads(prefs_str) if prefs_str else {}
    except json.JSONDecodeError:
        user_prefs = {}

    # Check ACL if premium_only is enabled
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("smart_recommendations")
        premium_only = config.get("premium_only", False)
        algorithm = config.get("algorithm", "hybrid")
    except Exception:
        premium_only = False
        algorithm = "hybrid"

    # Check user access (in real implementation, check against ACL)
    user_id = user_prefs.get("user_id", "anonymous")
    is_premium = user_prefs.get("is_premium", False)

    if premium_only and not is_premium:
        return "This feature is available for premium users only. Please upgrade your account."

    # Determine A/B test variant
    variant = "control"
    if player and hasattr(player, 'plugin_registry'):
        registry = player.plugin_registry
        variant = registry.get_ab_test_variant("smart_recommendations")

    # Get items for category
    if category == "general":
        # Mix all categories
        all_items = []
        for cat_items in SAMPLE_ITEMS.values():
            all_items.extend(cat_items)
        items = all_items
    else:
        items = SAMPLE_ITEMS.get(category, SAMPLE_ITEMS["movies"])

    if not items:
        return f"No recommendations available for category: {category}"

    # Apply recommendation algorithm based on variant
    if variant == "a":
        # Variant A: Popularity-based
        recommendations = popularity_based(items, count)
        algo_name = "Popularity (Variant A)"
    else:
        # Variant B: Hybrid (preferences + popularity)
        recommendations = hybrid_recommendations(items, user_prefs, count)
        algo_name = "Hybrid (Variant B)"

    # Record A/B test result (success if user gets recommendations)
    if player and hasattr(player, 'plugin_registry'):
        registry = player.plugin_registry
        registry.record_ab_test_result("smart_recommendations", variant, True)

    # Format response
    result = f"Recommendations ({algo_name}):\n\n"
    for i, item in enumerate(recommendations, 1):
        if "title" in item:
            result += f"{i}. {item['title']}"
            if "genre" in item:
                result += f" ({item['genre']})"
            if "year" in item:
                result += f" - {item['year']}"
            if "rating" in item:
                result += f" ⭐ {item['rating']}"
            if "author" in item:
                result += f" by {item['author']}"
            if "artist" in item:
                result += f" by {item['artist']}"
            if "cuisine" in item:
                result += f" - {item['cuisine']}"
            if "price" in item:
                result += f" {item['price']}"
            result += "\n"
        elif "name" in item:
            result += f"{i}. {item['name']} ({item['cuisine']}) ⭐ {item['rating']} {item['price']}\n"

    result += f"\nUser: {user_id} | Premium: {is_premium} | Variant: {variant.upper()}"

    if player:
        player.write_log(f"JARVIS: Generated {len(recommendations)} recommendations for {user_id}")

    return result


def popularity_based(items, count):
    """Recommend based on popularity (rating)."""
    # Sort by rating descending
    sorted_items = sorted(items, key=lambda x: x.get("rating", 0), reverse=True)
    return sorted_items[:count]


def hybrid_recommendations(items, user_prefs, count):
    """Hybrid recommendation using preferences and popularity."""
    # Get user's preferred genres
    preferred_genres = user_prefs.get("preferred_genres", [])
    preferred_artists = user_prefs.get("preferred_artists", [])

    scored_items = []
    for item in items:
        score = item.get("rating", 0) / 10  # Normalize rating

        # Boost for preferred genres
        if "genre" in item and item["genre"] in preferred_genres:
            score += 0.3
        if "genre" in item and any(g in item["genre"] for g in preferred_genres):
            score += 0.2

        # Boost for preferred artists/authors
        if "artist" in item and item["artist"] in preferred_artists:
            score += 0.4
        if "author" in item and item["author"] in preferred_artists:
            score += 0.4

        scored_items.append((score, item))

    # Sort by score
    scored_items.sort(key=lambda x: x[0], reverse=True)
    return [item for score, item in scored_items[:count]]


def on_load():
    print("[SYS] [PluginLoader] smart_recommendations: on_load hook called")


def on_enable():
    print("[SYS] [PluginLoader] smart_recommendations: on_enable hook called")


def on_disable():
    print("[SYS] [PluginLoader] smart_recommendations: on_disable hook called")


def on_unload():
    print("[SYS] [PluginLoader] smart_recommendations: on_unload hook called")


def on_reload():
    print("[SYS] [PluginLoader] smart_recommendations: on_reload hook called")