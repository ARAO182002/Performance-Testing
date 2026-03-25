def detect_root_cause(results):

    if not results:
        return None

    failing_apis = []

    for r in results:

        if r.get("status", 200) >= 400:
            failing_apis.append(r["api"])

    if not failing_apis:
        return None

    root_api = failing_apis[0]

    return {
        "root_cause_api": root_api,
        "affected_apis": failing_apis[1:]
    }