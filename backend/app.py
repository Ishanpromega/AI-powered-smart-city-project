
from flask import (
    Flask,
    request,
    jsonify,
    send_from_directory,
    session
)
from openai import OpenAI
from dotenv import load_dotenv
from ddgs import DDGS
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4, UUID
from functools import wraps
import os
import threading
import secrets
import psycopg
import re


# --------------------------------
# ENVIRONMENT CONFIGURATION
# --------------------------------

load_dotenv(Path(__file__).with_name(".env"))

api_key = os.getenv("OPENROUTER_API_KEY")
device_token = os.getenv("AETHER_DEVICE_TOKEN")

admin_password = os.getenv("AETHER_ADMIN_PASSWORD")
secret_key = os.getenv("AETHER_SECRET_KEY")


# --------------------------------
# OPENROUTER AI CONNECTION
# --------------------------------

client = OpenAI(
    api_key=api_key,
    base_url="https://openrouter.ai/api/v1"
) if api_key else None


# --------------------------------
# PROJECT CONFIGURATION
# --------------------------------

PROJECT_FOLDER = Path(__file__).resolve().parent.parent
WEBSITE_FOLDER = PROJECT_FOLDER / "mobile_app"

app = Flask(__name__)

app.secret_key = secret_key

app.config["MAX_CONTENT_LENGTH"] = 4096
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("AETHER_COOKIE_SECURE", "false").lower() == "true"
)
app.config["PERMANENT_SESSION_LIFETIME"] = 3600


# --------------------------------
# DEVICE STORAGE
# --------------------------------

device_data = {}
device_data_lock = threading.Lock()


# --------------------------------
# POSTGRESQL DATABASE
# --------------------------------

def get_db_connection():

    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5
    )


# --------------------------------
# VISITOR SESSION HELPERS
# --------------------------------

def create_visitor_session(session_id=None):

    if session_id:
        session_id = str(UUID(str(session_id)))
    else:
        session_id = str(uuid4())

    with get_db_connection() as conn:

        conn.execute("""
            INSERT INTO visitor_sessions
                (session_id, started_at, last_active)
            VALUES (%s, NOW(), NOW())

            ON CONFLICT (session_id)
            DO UPDATE SET last_active = NOW()
        """, (session_id,))

    return session_id


def save_user_message_and_get_history(session_id, message):

    with get_db_connection() as conn:

        visitor = conn.execute("""
            SELECT session_id
            FROM visitor_sessions
            WHERE session_id = %s
        """, (session_id,)).fetchone()

        if not visitor:
            raise ValueError("Visitor session does not exist.")

        conn.execute("""
            INSERT INTO conversation_messages
                (session_id, role, message)
            VALUES (%s, %s, %s)
        """, (session_id, "user", message))

        conn.execute("""
            UPDATE visitor_sessions
            SET last_active = NOW()
            WHERE session_id = %s
        """, (session_id,))

        rows = conn.execute("""
            SELECT role, message
            FROM conversation_messages
            WHERE session_id = %s
            ORDER BY message_id DESC
            LIMIT 12
        """, (session_id,)).fetchall()

        history = [
            {
                "role": row[0],
                "content": row[1]
            }
            for row in reversed(rows)
        ]

    return history


def save_assistant_message(session_id, reply):

    with get_db_connection() as conn:

        conn.execute("""
            INSERT INTO conversation_messages
                (session_id, role, message)
            VALUES (%s, %s, %s)
        """, (session_id, "assistant", reply))

        conn.execute("""
            UPDATE visitor_sessions
            SET last_active = NOW()
            WHERE session_id = %s
        """, (session_id,))


# --------------------------------
# VISITOR QUESTION ANALYTICS
# --------------------------------

def record_question_analytics(message):

    text = message.lower()

    topic_keywords = {

        "Weather": [
            "weather",
            "temperature",
            "rain",
            "climate",
            "forecast"
        ],

        "Traffic": [
            "traffic",
            "road",
            "vehicle",
            "signal",
            "transport"
        ],

        "Agriculture": [
            "soil",
            "plant",
            "crop",
            "agriculture",
            "farming",
            "moisture"
        ],

        "Security": [
            "security",
            "motion",
            "pir",
            "intruder",
            "surveillance"
        ],

        "Technology": [
            "technology",
            "computer",
            "robot",
            "internet",
            "software",
            "hardware"
        ],

        "Artificial Intelligence": [
            "artificial intelligence",
            "machine learning",
            "chatbot",
            "neural network",
            " ai "
        ]
    }

    detected_topic = "General"
    padded_text = " " + text + " "

    for topic, keywords in topic_keywords.items():

        if any(
            re.search(
                r"\b" + re.escape(keyword.strip()) + r"\b",
                padded_text
            )
            for keyword in keywords
        ):

            detected_topic = topic
            break

    try:

        with get_db_connection() as conn:

            conn.execute("""
                INSERT INTO question_analytics
                    (topic, question_count, updated_at)
                VALUES (%s, 1, NOW())

                ON CONFLICT (topic)

                DO UPDATE SET
                    question_count =
                        question_analytics.question_count + 1,
                    updated_at = NOW()
            """, (detected_topic,))

        return True

    except Exception as error:

        print("Analytics error:", error)
        return False


# --------------------------------
# PRIVATE ADMIN AUTHENTICATION
# --------------------------------

def require_admin(function):

    @wraps(function)
    def decorated_function(*args, **kwargs):

        if not session.get("aether_admin"):

            return jsonify({
                "error": "Admin login required."
            }), 401

        return function(*args, **kwargs)

    return decorated_function


@app.post("/api/admin/login")
def admin_login():

    if not app.secret_key:

        return jsonify({
            "error": "Admin session security is not configured."
        }), 503

    if not admin_password:

        return jsonify({
            "error": "Admin password is not configured."
        }), 503

    data = request.get_json(silent=True)

    if not isinstance(data, dict):

        return jsonify({
            "error": "Invalid request."
        }), 400

    supplied_password = data.get("password", "")

    if (
        not isinstance(supplied_password, str)
        or not secrets.compare_digest(
            supplied_password,
            admin_password
        )
    ):

        return jsonify({
            "error": "Incorrect admin password."
        }), 401

    session.clear()
    session.permanent = True
    session["aether_admin"] = True

    response = jsonify({
        "status": "success",
        "message": "Admin login successful."
    })

    response.headers["Cache-Control"] = "no-store"

    return response, 200


@app.post("/api/admin/logout")
def admin_logout():

    session.clear()

    return jsonify({
        "status": "success",
        "message": "Admin logged out."
    }), 200


# --------------------------------
# PRIVATE ANALYTICS API
# --------------------------------

@app.get("/api/analytics")
@require_admin
def get_analytics():

    try:

        with get_db_connection() as conn:

            total_questions = conn.execute("""
                SELECT COALESCE(SUM(question_count), 0)
                FROM question_analytics
            """).fetchone()[0]

            total_topics = conn.execute("""
                SELECT COUNT(*)
                FROM question_analytics
            """).fetchone()[0]

            total_visitors = conn.execute("""
                SELECT COUNT(*)
                FROM visitor_sessions
            """).fetchone()[0]

            topic_rows = conn.execute("""
                SELECT topic, question_count
                FROM question_analytics
                ORDER BY question_count DESC, topic ASC
            """).fetchall()

        topics = [
            {
                "topic": row[0],
                "questions": row[1]
            }
            for row in topic_rows
        ]

        most_popular = topics[0] if topics else None

        response = jsonify({
            "status": "success",
            "total_questions": total_questions,
            "total_topics": total_topics,
            "total_visitors": total_visitors,
            "most_popular_topic": most_popular,
            "topics": topics
        })

        response.headers["Cache-Control"] = "no-store"

        return response, 200

    except Exception as error:

        print("Analytics API error:", error)

        return jsonify({
            "error": "Could not retrieve analytics."
        }), 503


# --------------------------------
# CLEAR QUESTION ANALYTICS
# --------------------------------

@app.post("/api/admin/analytics/clear")
@require_admin
def clear_analytics():

    try:

        with get_db_connection() as conn:

            result = conn.execute("""
                DELETE FROM question_analytics
            """)

            deleted_topics = result.rowcount

        response = jsonify({
            "status": "success",
            "message": "Analytics cleared successfully.",
            "deleted_topics": deleted_topics
        })

        response.headers["Cache-Control"] = "no-store"

        return response, 200

    except Exception as error:

        print("Clear analytics error:", error)

        return jsonify({
            "error": "Could not clear analytics."
        }), 503


# --------------------------------
# WEBSITE
# --------------------------------

# --------------------------------
# WEBSITE
# --------------------------------

@app.get("/")
def home():

    return send_from_directory(
        WEBSITE_FOLDER,
        "index.html"
    )


# --------------------------------
# PRIVATE ADMIN DASHBOARD PAGE
# --------------------------------

@app.get("/admin")
@app.get("/admin/")
def admin_page():

    return send_from_directory(
        WEBSITE_FOLDER,
        "admin.html"
    )

@app.get("/<path:filename>")
def website_files(filename):

    return send_from_directory(
        WEBSITE_FOLDER,
        filename
    )


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
        supplied_token,
        expected_token
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
# DATABASE STATUS
# --------------------------------

@app.get("/api/database/status")
def database_status():

    try:

        with get_db_connection() as conn:
            conn.execute("SELECT 1")

        return jsonify({
            "status": "connected",
            "database": "AETHER"
        }), 200

    except Exception as error:

        print("Database connection error:", error)

        return jsonify({
            "status": "unavailable"
        }), 503


# --------------------------------
# VISITOR SESSIONS
# --------------------------------

@app.post("/api/session/start")
def start_visitor_session():

    data = request.get_json(silent=True)

    if data is None:
        data = {}

    if not isinstance(data, dict):

        return jsonify({
            "error": "Invalid request."
        }), 400

    supplied_id = data.get("session_id")

    try:

        session_id = create_visitor_session(supplied_id)

        return jsonify({
            "status": "success",
            "session_id": session_id
        }), 200

    except (ValueError, TypeError, AttributeError):

        return jsonify({
            "error": "Invalid session ID."
        }), 400

    except Exception as error:

        print("Visitor session error:", error)

        return jsonify({
            "error": "Could not create visitor session."
        }), 503


# --------------------------------
# AETHER AI CHAT + MEMORY + ANALYTICS
# --------------------------------

@app.post("/api/chat")
@app.post("/chat")
def chat():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        data = {}

    message = data.get("message", "")
    supplied_session_id = data.get("session_id")

    if not isinstance(message, str) or not message.strip():

        return jsonify({
            "reply": "Please enter a message."
        }), 400

    message = message.strip()

    if len(message) > 3000:

        return jsonify({
            "reply": "Your message is too long."
        }), 400

    if not client:

        return jsonify({
            "reply": "AETHER AI is not configured. Please check the server API settings."
        }), 503

    # Validate visitor session.

    try:

        if not supplied_session_id:

            return jsonify({
                "reply": "Visitor session is missing. Please refresh AETHER."
            }), 400

        session_id = str(UUID(str(supplied_session_id)))

    except (ValueError, TypeError, AttributeError):

        return jsonify({
            "reply": "Invalid visitor session. Please refresh AETHER."
        }), 400

    # Save visitor message and retrieve history.

    try:

        conversation_history = save_user_message_and_get_history(
            session_id,
            message
        )

    except ValueError:

        return jsonify({
            "reply": "Visitor session was not found. Please refresh AETHER."
        }), 404

    except Exception as error:

        print("Conversation database error:", error)

        return jsonify({
            "reply": "AETHER database is temporarily unavailable. Your message was not saved. Please try again."
        }), 503

    # Record analytics without interrupting chat.

    analytics_saved = record_question_analytics(message)

    # NEWS SEARCH

    search_context = ""

    if needs_search(message):

        query = build_search_query(message)

        search_context = get_search_results(
            query,
            worldwide=is_worldwide(message)
        )

    # DEVICE INFORMATION

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

    # AI SYSTEM PROMPT

    system_prompt = """
You are AETHER, an AI assistant for a futuristic smart city project.

Your default news and search region is India.
Use worldwide information when the user explicitly requests it.

Be helpful, clear, friendly and concise.

You may use the conversation history to understand references
to earlier messages in the same visitor session.

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

    # GENERATE AI RESPONSE

    try:

        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]

        messages.extend(conversation_history)

        response = client.chat.completions.create(
            model=os.getenv(
                "OPENROUTER_MODEL",
                "openai/gpt-4o-mini"
            ),
            messages=messages,
            max_tokens=500
        )

        reply = (
            response.choices[0].message.content
            or "I couldn't generate a response."
        )

        # Save AETHER response.

        memory_saved = True

        try:

            save_assistant_message(
                session_id,
                reply
            )

        except Exception as error:

            memory_saved = False

            print("Assistant message database error:", error)

        return jsonify({
            "reply": reply,
            "memory_saved": memory_saved,
            "analytics_saved": analytics_saved
        }), 200

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
