"""
Text Processor Plugin — demonstrates sandboxed text processing with resource limits.
"""

PLUGIN = {
    "name": "text_processor",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["text", "processing", "nlp", "sandbox", "analysis"],
    "dependencies": [],
    "min_jarvis_version": "1.2.0",
    "description": (
        "Process and analyze text in a sandboxed environment. "
        "Trigger with phrases like 'analyze text', 'process text', 'count words', "
        "'extract keywords', 'summarize text'. Runs in isolated subprocess with "
        "CPU, memory, and time limits for security."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {
                "type": "STRING",
                "description": "Text to process",
            },
            "operation": {
                "type": "STRING",
                "description": "Processing operation",
                "enum": ["count", "keywords", "summary", "sentiment", "clean"],
                "default": "count",
            },
            "language": {
                "type": "STRING",
                "description": "Language code (en, pt, es, fr, de)",
                "default": "en",
            },
        },
        "required": ["text"],
    },
    "capabilities": [],
    "sandboxed": True,
    "sandbox_timeout": 30,
    "sandbox_memory_mb": 128,
    # Resource quotas for additional safety
    "cpu_quota_percent": 50.0,
    "memory_quota_mb": 200,
    "disk_quota_mb": 100,
    # Enable audit logging for this plugin
    "audit_log": True,
}

# Settings schema for UI configuration
PLUGIN_SETTINGS = {
    "namespace": "text_processor",
    "title": "Text Processor Configuration",
    "fields": [
        {
            "key": "max_text_length",
            "label": "Max Text Length",
            "type": "integer",
            "default": 10000,
            "min": 1000,
            "max": 100000,
        },
        {
            "key": "default_language",
            "label": "Default Language",
            "type": "choice",
            "choices": ["en", "pt", "es", "fr", "de", "auto"],
            "default": "en",
        },
        {
            "key": "enable_keywords",
            "label": "Enable Keyword Extraction",
            "type": "boolean",
            "default": True,
        },
    ],
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Process text in sandboxed environment."""
    text = parameters.get("text", "")
    operation = parameters.get("operation", "count")
    language = parameters.get("language", "en")

    if not text:
        return "Please provide text to process."

    # Limit text length
    max_length = 10000
    try:
        from memory.config_manager import get_plugin_config
        config = get_plugin_config("text_processor")
        max_length = config.get("max_text_length", 10000)
    except Exception:
        pass

    if len(text) > max_length:
        text = text[:max_length]
        return f"Text truncated to {max_length} characters. Please provide shorter text."

    # Simple text processing operations
    if operation == "count":
        words = text.split()
        chars = len(text)
        lines = text.count('\n') + 1
        paragraphs = len([p for p in text.split('\n\n') if p.strip()])
        return (f"Text Statistics:\n"
                f"  Characters: {chars}\n"
                f"  Words: {len(words)}\n"
                f"  Lines: {lines}\n"
                f"  Paragraphs: {paragraphs}\n"
                f"  Avg word length: {sum(len(w) for w in words) / len(words):.1f}")

    elif operation == "keywords":
        # Simple keyword extraction (frequency-based)
        import re
        from collections import Counter

        # Clean and tokenize
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())

        # Common stop words
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had',
            'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his',
            'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who',
            'boy', 'did', 'let', 'put', 'say', 'she', 'too', 'use', 'com', 'org',
            'this', 'that', 'with', 'have', 'from', 'they', 'will', 'been', 'were',
            'said', 'each', 'which', 'their', 'time', 'would', 'there', 'what',
            'could', 'other', 'than', 'first', 'these', 'people', 'most', 'some',
            'over', 'many', 'then', 'them', 'these', 'so', 'up', 'no', 'if', 'about',
            'out', 'into', 'than', 'them', 'only', 'when', 'here', 'your', 'more',
            'very', 'after', 'just', 'any', 'now', 'like', 'than', 'also', 'back',
            'even', 'still', 'might', 'where', 'every', 'must', 'never', 'found',
            'long', 'while', 'little', 'should', 'something', 'without', 'between',
            'during', 'before', 'again', 'always', 'another', 'because', 'number',
            'since', 'whatever', 'several', 'almost', 'enough', 'sometimes', 'mean',
        }

        filtered = [w for w in words if w not in stop_words and len(w) > 3]
        freq = Counter(filtered)
        top_keywords = freq.most_common(10)

        if not top_keywords:
            return "No keywords found."

        result = "Top Keywords:\n"
        for word, count in top_keywords:
            result += f"  {word}: {count}\n"
        return result

    elif operation == "summary":
        # Simple extractive summary (first N sentences)
        import re
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) <= 3:
            return "Text is already short. Full text:\n" + text

        summary = '. '.join(sentences[:3]) + '.'
        return f"Summary (first 3 sentences):\n{summary}\n\nOriginal length: {len(sentences)} sentences"

    elif operation == "sentiment":
        # Simple sentiment analysis (word-based)
        positive_words = {'good', 'great', 'excellent', 'amazing', 'wonderful', 'fantastic',
                         'happy', 'joy', 'love', 'like', 'best', 'awesome', 'brilliant',
                         'beautiful', 'perfect', 'positive', 'success', 'win', 'great'}
        negative_words = {'bad', 'terrible', 'awful', 'horrible', 'sad', 'angry', 'hate',
                         'dislike', 'worst', 'poor', 'negative', 'fail', 'lose', 'wrong',
                         'problem', 'issue', 'error', 'bug', 'broken', 'useless'}

        words = text.lower().split()
        pos_count = sum(1 for w in words if w in positive_words)
        neg_count = sum(1 for w in words if w in negative_words)

        if pos_count > neg_count:
            sentiment = "Positive"
        elif neg_count > pos_count:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"

        return (f"Sentiment Analysis:\n"
                f"  Sentiment: {sentiment}\n"
                f"  Positive words: {pos_count}\n"
                f"  Negative words: {neg_count}\n"
                f"  Score: {pos_count - neg_count}")

    elif operation == "clean":
        # Clean text (remove extra whitespace, normalize)
        import re
        cleaned = re.sub(r'\s+', ' ', text).strip()
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return f"Cleaned text:\n{cleaned}"

    else:
        return f"Unknown operation: {operation}"


def on_load():
    print("[SYS] [PluginLoader] text_processor: on_load hook called")


def on_enable():
    print("[SYS] [PluginLoader] text_processor: on_enable hook called")


def on_disable():
    print("[SYS] [PluginLoader] text_processor: on_disable hook called")


def on_unload():
    print("[SYS] [PluginLoader] text_processor: on_unload hook called")


def on_reload():
    print("[SYS] [PluginLoader] text_processor: on_reload hook called")