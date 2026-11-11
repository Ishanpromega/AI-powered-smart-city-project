
from flask import Flask, request, jsonify, send_from_directory
from openai import OpenAI
from dotenv import load_dotenv
from ddgs import DDGS
from pathlib import Path
from datetime import datetime, timezone
import os
import threading
import secrets

# Load environment variables
load_dotenv(Path(__file__).with_name(".env"))

api_key = os.getenv("OPENROUTER_API_KEY")
device_token = os.getenv("AETHER_DEVICE_TOKEN")

# OpenRouter AI connection
client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
) if api_key else None

# Project folders
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
WEBSITE_FOLDER = PROJECT_FOLDER / "mobile_app"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4096

# Temporary device storage
device_data = {}
device_data_lock = threading.Lock()


# --------------------------------
# WEBSITE
# --------------------------------

@app.get("/")
def home():
    return send_from_directory(WEBSITE_FOLDER, "index.html")


@app.get("/<path:filename>")
def website_files(filename):
    return send_from_directory(WEBSITE_FOLDER, filename)


# --------------------------------
# NEWS SEARCH
# --------------------------------

def needs_search(message):
    keywords = [
        "search the web",
        "search for",
        "latest",
        "recent",
        "today",
        "currently",
        "current",
        "this week",
        "news",
        "happening now"
    ]

    message = message.lower()
    return any(word in message for word in keywords)


def is_worldwide(message):
    keywords = [
        "worldwide",
        "world wide",
        "global news",
        "international news",
        "around the world"
    ]

    message = message.lower()
    return any(word in message for word in keywords)


def build_search_query(message):
    query = message.replace(
        "Search the web for:", ""
    ).strip()

    country_words = [
        "india",
        "indian",
        "usa",
        "america",
        "japan",
        "china",
        "uk",
        "britain",
        "germany",
        "france",
        "russia",
        "south korea",
        "australia"
    ]

    if is_worldwide(message):
        return query

    if any(word in query.lower() for word in country_words):
        return query

    return query + " India"


def get_search_results(query, worldwide=False):
    region = "wt-wt" if worldwide else "in-en"

    try:
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

        return "\n\n".join(formatted)

    except Exception as error:
        print("News search error:", error)
        return ""


# --------------------------------
# DEVICE AUTHENTICATION
# --------------------------------

def require_device_token():
    expected_token = os.getenv("AETHER_DEVICE_TOKEN")

    auth_header = request.headers.get(
        "Authorization", ""
    )

    supplied_token = ""

    if auth_header.startswith("Bearer "):
        supplied_token = auth_header[7:].strip()

    if not expected_token:
        return jsonify({
            "error": "Device access is not configured."
        }), 503

    if not supplied_token or not secrets.compare_digest(
        supplied_token, expected_token
    ):
        return jsonify({
            "error": "Unauthorized device."
        }), 401

    return None


# --------------------------------
# RECEIVE ESP8266 DATA
# --------------------------------

@app.post("/api/device/data")
def receive_device_data():

    auth_error = require_device_token()

    if auth_error:
        return auth_error

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Send a valid JSON object."
        }), 400

    device_id = data.get("device_id")
    readings = data.get("readings")

    if (
        not isinstance(device_id, str)
        or not device_id.strip()
        or len(device_id) > 40
    ):
        return jsonify({
            "error": "A valid device_id is required."
        }), 400

    if (
        not isinstance(readings, dict)
        or not readings
        or len(readings) > 20
    ):
        return jsonify({
            "error": "Invalid readings."
        }), 400

    clean_readings = {}

    for key, value in readings.items():

        if (
            not isinstance(key, str)
            or not key
            or len(key) > 40
        ):
            return jsonify({
                "error": "Invalid reading name."
            }), 400

        if isinstance(value, (bool, int, float)):
            clean_readings[key] = value

        elif isinstance(value, str) and len(value) <= 80:
            clean_readings[key] = value

        else:
            return jsonify({
                "error": "Invalid reading value."
            }), 400

    received_at = datetime.now(
        timezone.utc
    ).isoformat()

    with device_data_lock:
        device_data[device_id] = {
            "readings": clean_readings,
            "received_at": received_at
        }

    return jsonify({
        "status": "success",
        "device_id": device_id,
        "received_at": received_at
    }), 200


# --------------------------------
# GET DEVICE STATUS
# --------------------------------

@app.get("/api/device/status")
def get_device_status():

    auth_error = require_device_token()

    if auth_error:
        return auth_error

    current_time = datetime.now(timezone.utc)

    devices = {}

    with device_data_lock:

        for device_id, information in device_data.items():

            received_at = datetime.fromisoformat(
                information["received_at"]
            )

            age = (
                current_time - received_at
            ).total_seconds()

            devices[device_id] = {
                "online": age <= 90,
                "readings": information["readings"],
                "received_at": information["received_at"],
                "seconds_since_update": round(age, 1)
            }

    return jsonify({
        "status": "success",
        "devices": devices
    }), 200


# --------------------------------
# AETHER AI CHAT
# --------------------------------

@app.post("/api/chat")
@app.post("/chat")
def chat():

    data = request.get_json(silent=True) or {}

    message = data.get("message", "")

    if not isinstance(message, str) or not message.strip():
        return jsonify({
            "reply": "Please enter a message."
        }), 400

    if len(message) > 3000:
        return jsonify({
            "reply": "Your message is too long."
        }), 400

    if not client:
        return jsonify({
            "reply": "AETHER AI is not configured. Please check the server API settings."
        }), 503

    search_context = ""

    # Search when the question needs current information
    if needs_search(message):

        query = build_search_query(message)

        search_context = get_search_results(
            query,
            worldwide=is_worldwide(message)
        )

    # Add latest device readings as AI context
    device_context = ""

    with device_data_lock:
        current_devices = dict(device_data)

    if current_devices:

        device_context = "\n\nLATEST DEVICE INFORMATION:\n"

        current_time = datetime.now(timezone.utc)

        for device_id, information in current_devices.items():

            received_at = datetime.fromisoformat(
                information["received_at"]
            )

            age = (
                current_time - received_at
            ).total_seconds()

            online = age <= 90

            device_context += (
                f"\nDevice: {device_id}"
                f"\nOnline: {online}"
                f"\nReadings: {information['readings']}\n"
            )

    system_prompt = """
You are AETHER, an AI assistant for a futuristic smart city project.

Your default news and search region is India.
Use worldwide information when the user explicitly requests it.

Be helpful, clear, friendly and concise.

When device information is provided, use only the readings shown.
Never invent sensor values.

You cannot directly control hardware unless a real device-control
system confirms that the command was executed.

Do not claim that a light, motor, relay or other device has been
turned on or off unless execution has actually been confirmed.
"""

    if search_context:
        system_prompt += (
            "\n\nCURRENT WEB SEARCH RESULTS:\n"
            + search_context
        )

    if device_context:
        system_prompt += device_context

    try:

        response = client.chat.completions.create(
            model=os.getenv(
                "OPENROUTER_MODEL",
                "openai/gpt-4o-mini"
            ),
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            max_tokens=500
        )

        reply = response.choices[0].message.content

        return jsonify({
            "reply": reply or "I couldn't generate a response."
        })

    except Exception as error:

        print("AI error:", error)

        return jsonify({
            "reply": "AETHER encountered an AI connection error. Please try again."
        }), 500


# --------------------------------
# HEALTH CHECK
# --------------------------------

@app.get("/health")
def health():

    return jsonify({
        "status": "online",
        "project": "PROJECT AETHER"
    })


# --------------------------------
# START SERVER
# --------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=False
    )
