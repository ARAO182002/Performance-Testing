from ai_engine.correlation_engine import detect_dynamic_fields
from ai_engine.correlation_engine import detect_correlation_issue


def analyze_api_result(api, status, response_time, response):

    # -------------------------------
    # SAFETY CHECK
    # -------------------------------
    if response is None:
        response = ""

    # -------------------------------
    # DETECT DYNAMIC & CORRELATION ISSUES
    # -------------------------------
    dynamic_fields = detect_dynamic_fields(response)
    correlation_issue = detect_correlation_issue(status, response)

    # -------------------------------
    # STATUS-BASED ANALYSIS
    # -------------------------------
    if 100 <= status < 200:
        analysis = {
            "type": "Informational Response",
            "severity": "Low",
            "reason": f"HTTP {status} indicates informational response",
            "suggestion": "Check if the API call completed properly"
        }

    elif 200 <= status < 300:

        if response_time > 2000:
            analysis = {
                "type": "Critical Slow API",
                "severity": "High",
                "reason": f"Response time {response_time} ms is extremely high",
                "suggestion": "Immediate investigation required"
            }

        elif response_time > 1000:
            analysis = {
                "type": "Performance Warning",
                "severity": "Medium",
                "reason": f"API succeeded but response time is high ({response_time} ms)",
                "suggestion": "Investigate backend performance"
            }

        else:
            analysis = {
                "type": "Success",
                "severity": "Low",
                "reason": f"HTTP {status} indicates successful request",
                "suggestion": "API executed successfully"
            }

    elif 300 <= status < 400:
        analysis = {
            "type": "Redirection",
            "severity": "Low",
            "reason": f"HTTP {status} indicates redirection",
            "suggestion": "Verify redirection behavior"
        }

    elif 400 <= status < 500:

        if status == 401:
            error = "Unauthorized"
            suggestion = "Check authentication token"

        elif status == 403:
            error = "Forbidden"
            suggestion = "Check permissions"

        elif status == 404:
            error = "Not Found"
            suggestion = "Verify API endpoint"

        elif status == 429:
            error = "Too Many Requests"
            suggestion = "Rate limit exceeded"

        else:
            error = "Client Error"
            suggestion = "Check request payload"

        analysis = {
            "type": "Client Error",
            "severity": "Medium",
            "error": error,
            "reason": f"HTTP {status}",
            "suggestion": suggestion
        }

    elif 500 <= status < 600:
        analysis = {
            "type": "Server Error",
            "severity": "High",
            "reason": f"HTTP {status}",
            "suggestion": "Check backend logs"
        }

    else:
        analysis = {
            "type": "Unknown Status Code",
            "severity": "Low",
            "reason": f"Unexpected HTTP {status}"
        }


    # -------------------------------
    # EXTRA RESPONSE INTELLIGENCE
    # -------------------------------
    response_lower = response.lower()

    if "token expired" in response_lower:
        analysis["extra"] = "Authentication token expired"

    if "exception" in response_lower:
        analysis["extra"] = "Server exception detected"

    # -------------------------------
    # FINAL OUTPUT
    # -------------------------------
    return {
        "api": api,
        "status": status,
        "response_time": response_time,
        "response": response[:200],  # prevent large payload
        "analysis": analysis,
        "dynamic_fields_detected": dynamic_fields,
        "correlation_issue": correlation_issue
    }