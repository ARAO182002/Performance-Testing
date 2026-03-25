import re
import json

def detect_dynamic_fields(response):
    if not response:
        return []

    dynamic_fields = set()

    # 1. Try JSON parsing
    try:
        data = json.loads(response)

        def extract_keys(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if any(k in key.lower() for k in ["id", "token", "session", "key"]):
                        dynamic_fields.add(key)
                    extract_keys(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_keys(item)

        extract_keys(data)

    except json.JSONDecodeError:
        pass

    # 2. Regex for HTML / text
    patterns = [
        r'name=["\'](.*?)["\']\s+value=["\'](.*?)["\']',
        r'\b([a-zA-Z0-9_]*id)\b\s*[:=]\s*["\']([a-zA-Z0-9\-]+)["\']',
        r'\b([a-zA-Z0-9_]*token)\b\s*[:=]\s*["\']([a-zA-Z0-9\-_.]+)["\']'
    ]

    for pattern in patterns:
        matches = re.findall(pattern, response)
        for match in matches:
            field_name = match[0]
            dynamic_fields.add(field_name)

    return list(dynamic_fields)


def detect_correlation_issue(status, response):
    if not response:
        return None

    response_lower = response.lower()

    if status in [401, 403]:
        return "Authentication/Authorization failure - possible missing dynamic token"

    if "invalid token" in response_lower:
        return "Invalid token - correlation missing"

    if "token expired" in response_lower:
        return "Token expired - regenerate dynamically"

    if "session expired" in response_lower:
        return "Session expired - correlation not handled"

    if "not found" in response_lower and "id" in response_lower:
        return "Dynamic ID missing or incorrect in request"

    return None