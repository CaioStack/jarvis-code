"""
Safe Calculator Plugin — demonstrates sandboxed execution.

This plugin runs in an isolated subprocess with resource limits,
demonstrating the Phase 2 sandbox feature for untrusted code.
"""

PLUGIN = {
    "name": "safe_calc",
    "version": "1.0.0",
    "author": "Jarvis-Code Team",
    "license": "MIT",
    "homepage": "https://github.com/jarvis-code/jarvis-code",
    "repository": "https://github.com/jarvis-code/jarvis-code",
    "keywords": ["calculator", "math", "sandbox", "safe", "eval"],
    "dependencies": [],
    "min_jarvis_version": "1.1.0",
    "description": (
        "Perform mathematical calculations safely in a sandboxed subprocess. "
        "Trigger with phrases like 'calculate', 'compute', 'what is 2 plus 2', "
        "'solve math problem'. The plugin runs in an isolated process with "
        "time and memory limits for security."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "expression": {
                "type": "STRING",
                "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(pi/2)')",
            },
        },
        "required": ["expression"],
    },
    "capabilities": [],  # No special capabilities needed - pure computation
    "sandboxed": True,   # Run in isolated subprocess
    "sandbox_timeout": 10,   # 10 second timeout
    "sandbox_memory_mb": 64, # 64 MB memory limit
}

# Allowed functions for safe evaluation
SAFE_FUNCTIONS = {
    # Basic math
    'abs': abs, 'round': round, 'min': min, 'max': max, 'sum': sum,
    # Power/roots
    'pow': pow,
    # Trigonometry (from math)
    'sin': None, 'cos': None, 'tan': None, 'asin': None, 'acos': None, 'atan': None,
    'sinh': None, 'cosh': None, 'tanh': None,
    # Logarithms/exponentials
    'log': None, 'log10': None, 'log2': None, 'exp': None, 'expm1': None,
    # Constants
    'pi': None, 'e': None, 'tau': None, 'inf': None, 'nan': None,
    # Other
    'sqrt': None, 'ceil': None, 'floor': None, 'trunc': None,
    'degrees': None, 'radians': None,
    'factorial': None, 'gcd': None, 'lcm': None,
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Evaluate a mathematical expression safely."""
    import math

    # Populate SAFE_FUNCTIONS with math module functions
    SAFE_FUNCTIONS.update({
        'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
        'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
        'log': math.log, 'log10': math.log10, 'log2': math.log2,
        'exp': math.exp, 'expm1': math.expm1,
        'pi': math.pi, 'e': math.e, 'tau': math.tau, 'inf': math.inf, 'nan': math.nan,
        'sqrt': math.sqrt, 'ceil': math.ceil, 'floor': math.floor, 'trunc': math.trunc,
        'degrees': math.degrees, 'radians': math.radians,
        'factorial': math.factorial, 'gcd': math.gcd, 'lcm': math.lcm,
    })

    expression = parameters.get("expression", "").strip()

    if not expression:
        return "Please provide a mathematical expression to evaluate."

    # Basic validation - only allow safe characters
    allowed_chars = set("0123456789+-*/()., abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
    if not all(c in allowed_chars for c in expression):
        return f"Sir, that expression contains invalid characters. Only numbers, basic operators, and math functions are allowed."

    try:
        # Evaluate in restricted namespace
        result = eval(expression, {"__builtins__": {}}, SAFE_FUNCTIONS)

        # Format result nicely
        if isinstance(result, float):
            if result == int(result):
                result_str = str(int(result))
            else:
                result_str = f"{result:.10g}"
        else:
            result_str = str(result)

        response = f"{expression} = {result_str}"

        if player:
            player.write_log(f"JARVIS: Calculated {expression} = {result_str}")

        return response

    except ZeroDivisionError:
        return "Sir, division by zero is not allowed."
    except OverflowError:
        return "Sir, the result is too large to compute."
    except SyntaxError:
        return f"Sir, that expression has a syntax error. Please check it and try again."
    except NameError as e:
        return f"Sir, unknown function or constant: {e}"
    except Exception as e:
        return f"Sir, calculation failed: {e}"