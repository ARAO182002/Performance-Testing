from fastapi import FastAPI
from pydantic import BaseModel
from ai_engine.analysis import analyze_api_result
from sse_starlette.sse import EventSourceResponse
import asyncio
from datetime import datetime
import pytz
import json
import re

# Timezone setup (IST)
ist = pytz.timezone("Asia/Kolkata")

# In-memory storage
results = []

# Create FastAPI app
app = FastAPI(title="AI JMeter Agent Backend")


# -------------------------------
# MODEL
# -------------------------------
class TestResult(BaseModel):
    api: str
    status: int
    response_time: float
    response: str
    request: str = ""


# -------------------------------
# STEP 5: SMART FILTER
# -------------------------------
def is_probably_dynamic(field, value, results):
    value = str(value)
    score = 0

    if value.isdigit() and int(value) < 10:
        score -= 2

    seen_values = set()
    for res in results:
        request = res.get("request", "").lower()
        match = re.search(f"{field}[=:\\\"]+(\\w+)", request)
        if match:
            seen_values.add(match.group(1))

    if len(seen_values) > 1:
        score += 3

    if len(value) > 8:
        score += 2

    if re.search(r'[a-zA-Z]', value) and re.search(r'\d', value):
        score += 2

    return score >= 2


# -------------------------------
# STEP 1: HARD-CODED DETECTION
# -------------------------------
def detect_hardcoded_dynamic_fields(request, response, results):
    issues = []

    if not request:
        return issues

    request_lower = request.lower()
    response_lower = response.lower() if response else ""

    DYNAMIC_FIELD_HINTS = [
        "orderid", "token", "session", "csrf",
        "auth", "requestid", "transactionid"
    ]

    for field in DYNAMIC_FIELD_HINTS:
        match = re.search(f"{field}[=:\\\"]+(\\w+)", request_lower)

        if match:
            value = match.group(1)

            if value not in response_lower and is_probably_dynamic(field, value, results):
                issues.append({
                    "field": field,
                    "value": value,
                    "issue": "Hardcoded but expected dynamic"
                })

    return issues


# -------------------------------
# STEP 2: FIND SOURCE API (FIXED)
# -------------------------------
def find_latest_field_source(field, results, current_api):
    field = field.lower()

    for res in reversed(results):
        if res.get("api") == current_api:
            continue

        response = res.get("response", "").lower()

        if field in response or "order no" in response:
            return res.get("api")

    return None


# -------------------------------
# STEP 2: CORRELATION SUGGESTIONS
# -------------------------------
def generate_correlation_suggestions(hardcoded_issues, results, current_api):
    suggestions = []

    for issue in hardcoded_issues:
        field = issue["field"]
        value = issue["value"]

        source_api = find_latest_field_source(field, results, current_api)

        suggestions.append({
            "field": field,
            "value": value,
            "variable_name": f"${{{field}}}",
            "extract_from": source_api if source_api else "Unknown",
            "use_in": current_api,
            "confidence": "High" if source_api else "Low",
            "reason": (
                f"{field} is hardcoded in {current_api} but appears to be generated in {source_api}"
                if source_api else
                f"{field} is hardcoded in {current_api} but no earlier source API was found"
            )
        })

    return suggestions


# -------------------------------
# STEP 3: API FLOW
# -------------------------------
def build_api_flow(current_request, results):
    flow = []

    if not current_request:
        return flow

    values = re.findall(r'[=:\"]([a-zA-Z0-9\-]+)', current_request.lower())

    for value in values:
        for past in reversed(results):
            response = past.get("response", "").lower()

            if value in response:
                flow.append({
                    "value": value,
                    "from_api": past.get("api")
                })
                break

    return flow


# -------------------------------
# STEP 4: EXTRACTORS
# -------------------------------
def generate_extractors(correlation_suggestions, results):
    extractors = []

    for suggestion in correlation_suggestions:
        field = suggestion["field"]
        source_api = suggestion["extract_from"]

        if source_api == "Unknown":
            continue

        response_text = ""

        for res in reversed(results):
            if res.get("api") == source_api:
                response_text = res.get("response", "")
                break

        if response_text.strip().startswith("{"):
            extractor_type = "JSON"
            expression = f"$.{field}"
        else:
            extractor_type = "Regex"
            expression = f"{field}=(\\w+)"

        extractors.append({
            "field": field,
            "extractor_type": extractor_type,
            "expression": expression,
            "apply_on": source_api
        })

    return extractors


# -------------------------------
# REAL-TIME STREAM
# -------------------------------
async def event_stream():
    previous_count = 0

    while True:
        if len(results) > previous_count:
            new_items = results[previous_count:len(results)]

            for item in new_items:
                yield {
                    "event": "new_result",
                    "data": json.dumps(item)
                }

            previous_count = len(results)

        await asyncio.sleep(0.2)


# -------------------------------
# HEALTH CHECK
# -------------------------------
@app.get("/")
def home():
    return {"message": "AI JMeter Agent Backend Running"}


# -------------------------------
# MAIN ANALYZE API
# -------------------------------
@app.post("/analyze")
def analyze(result: TestResult):

    analysis = analyze_api_result(
        api=result.api,
        status=result.status,
        response_time=result.response_time,
        response=result.response
    )

    hardcoded_issues = detect_hardcoded_dynamic_fields(
        result.request,
        result.response,
        results
    )

    correlation_suggestions = generate_correlation_suggestions(
        hardcoded_issues,
        results,
        result.api
    )

    flow = build_api_flow(result.request, results)
    for f in flow:
        f["to_api"] = result.api

    extractors = generate_extractors(correlation_suggestions, results)

    current_time = datetime.now(ist)

    analysis["timestamp"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    analysis["hardcoded_dynamic_issues"] = hardcoded_issues
    analysis["correlation_suggestions"] = correlation_suggestions
    analysis["api_flow"] = flow
    analysis["extractors"] = extractors

    results.append({
        "api": result.api,
        "request": result.request,
        "response": result.response,
        "analysis": analysis
    })

    return analysis


# -------------------------------
# VIEW RESULTS
# -------------------------------
@app.get("/results")
def get_results():
    return {
        "total_tests": len(results),
        "results": results
    }


# -------------------------------
# CLEAR RESULTS
# -------------------------------
@app.delete("/clear")
def clear_results():
    results.clear()
    return {"message": "Cleared"}


# -------------------------------
# LIVE STREAM
# -------------------------------
@app.get("/live-results")
async def stream_results():
    return EventSourceResponse(event_stream())


# -------------------------------
# COPILOT ENDPOINT
# -------------------------------
@app.get("/latest-analysis")
def latest_analysis():
    if not results:
        return {"message": "No results yet"}

    latest = results[-1]

    return {
        "api": latest["api"],
        "analysis": latest["analysis"],
        "hardcoded_dynamic_issues": latest["analysis"].get("hardcoded_dynamic_issues", []),
        "correlation_suggestions": latest["analysis"].get("correlation_suggestions", []),
        "api_flow": latest["analysis"].get("api_flow", []),
        "extractors": latest["analysis"].get("extractors", []),
        "summary_text": f"""
API: {latest["api"]}
Type: {latest["analysis"].get("type")}
Severity: {latest["analysis"].get("severity")}
Suggestion: {latest["analysis"].get("suggestion")}
"""
    }


# -------------------------------
# SUMMARY ENDPOINT
# -------------------------------
@app.get("/summary")
def summary():
    return {
        "total_results": len(results),
        "latest_5": [
            {
                "api": r["api"],
                "type": r["analysis"].get("type"),
                "severity": r["analysis"].get("severity")
            }
            for r in results[-5:]
        ]
    }