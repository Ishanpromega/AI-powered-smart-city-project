    ).strip()

    lower_query = query.lower()

    worldwide_words = [
        "worldwide",
        "world wide",
        "global news",
        "international news",
        "around the world"
    ]

    if any(word in lower_query for word in worldwide_words):
        return query

    country_words = [
        "india", "indian", "usa", "america",
        "japan", "china", "uk", "britain",
        "germany", "france", "russia",
        "south korea", "australia"
    ]

    if any(word in lower_query for word in country_words):
        return query

    return query + " India"


def get_search_results(query, worldwide=False):
    region = "wt-wt" if worldwide else "in-en"

    results = DDGS().news(
        query,
        region=region,
        safesearch="moderate",
        max_results=5
    )

    formatted = []

    for item in results:
        formatted.append(
            "Headline: " + item.get("title", "") +
            "\nDate: " + item.get("date", "") +
            "\nDescription: " + item.get("body", "") +
            "\nSource: " + item.get("source", "") +
            "\nURL: " + item.get("url", "")
        )

    if not formatted:
        return ""

    return "\n\n".join(formatted)


def require_device_token():
    expected_token = os.getenv("AETHER_DEVICE_TOKEN")
    auth_header = request.headers.get("Authorization", "")
    supplied_token = ""

    if auth_header.startswith("Bearer "):
        supplied_token = auth_header[7:].strip()

    if not expected_token:
        return jsonify({
            "error": "Device access is not configured on the server."
        }), 503

    if not supplied_token or not secrets.compare_digest(
        supplied_token, expected_token
    ):
        return jsonify({"error": "Unauthorized device."}), 401

    return None


@app.post("/api/device/data")
def receive_device_data():
    auth_error = require_device_token()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Send a JSON object."}), 400

    device_id = data.get("device_id")
    readings = data.get("readings")

    if not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 40:
        return jsonify({"error": "A valid device_id is required."}), 400

    if not isinstance(readings, dict) or not readings or len(readings) > 20:
        return jsonify({"error": "readings must be a non-empty JSON object."}), 400

    # Accept only simple values; do not store nested objects or large strings.
    clean_readings = {}
    for key, value in readings.items():
        if not isinstance(key, str) or not key or len(key) > 40:
            return jsonify({"error": "Invalid reading name."}), 400

        if isinstance(value, (bool, int, float)):
            clean_readings[key] = value
        elif isinstance(value, str) and len(value) <= 80:
            clean_readings[key] = value
        else:
            return jsonify({"error": "Readings must be short strings or numbers."}), 400

    received_at = datetime.now(timezone.utc).isoformat()

    with device_data_lock:
        device_data[device_id] = {
            "readings": clean_readings,
            "received_at": received_at,
            "received_timestamp": time.time()
        }

    return jsonify({
        "ok": True,
        "message": "AETHER received the device data.",
        "device_id": device_id,
        "received_at": received_at
    }), 200


@app.get("/api/device/status")
def get_device_status():
    auth_error = require_device_token()
    if auth_error:
        return auth_error

    with device_data_lock:
        snapshot = {
            device_id: {
                "readings": item["readings"],
                "received_at": item["received_at"],
                "online": (time.time() - item["received_timestamp"]) <= 90
            }
            for device_id, item in device_data.items()
        }

    return jsonify({"devices": snapshot}), 200


def get_city_device_context():
    with device_data_lock:
        snapshot = {
            device_id: dict(item)
            for device_id, item in device_data.items()
        }

    if not snapshot:
        return (
            "No device sensor data has been received by AETHER yet. "
            "Do not guess or invent device conditions."
        )

    now = time.time()
    lines = ["Latest smart-city device information received by AETHER:"]

    for device_id, item in snapshot.items():
        online = (now - item["received_timestamp"]) <= 90
        status = "ONLINE" if online else "STALE / NOT RECENTLY HEARD FROM"
        lines.append(
            f"Device: {device_id} | Status: {status} | "
            f"Last received: {item['received_at']} | "
            f"Readings: {item['readings']}"
        )

    lines.append(
        "Only report readings shown here. If data is stale, say it may be "
        "out of date. Never claim an actuator succeeded unless a device "
        "has explicitly reported its resulting state."
    )
    return "\n".join(lines)


@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Please enter a question."}), 400

    if len(message) > 2000:
        return jsonify({"error": "Question is too long."}), 400

    if client is None:
        return jsonify({"error": "OpenRouter API key is missing."}), 503

    search_context = ""