
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
# LOCATION SEARCH + WEATHER
# --------------------------------

@app.get("/api/location/search")
def search_location():
    query = request.args.get("q", "").strip()

    if not query or len(query) > 100:
        return jsonify({"error": "Enter a valid city or place name."}), 400

    params = urlencode({
        "name": query,
        "count": 6,
        "language": "en",
        "format": "json"
    })
    url = "https://geocoding-api.open-meteo.com/v1/search?" + params

    try:
        req = Request(url, headers={"User-Agent": "ProjectAETHER/1.0"})
        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))

        places = []
        for item in result.get("results", []):
            places.append({
                "name": item.get("name", ""),
                "admin1": item.get("admin1", ""),
                "country": item.get("country", ""),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude")
            })

        return jsonify({"status": "success", "results": places})

    except (URLError, HTTPError, TimeoutError, ValueError) as error:
        print("Location search error:", error)
        return jsonify({"error": "Location search is temporarily unavailable."}), 502


@app.get("/api/weather")
def get_weather():
    try:
        latitude = float(request.args.get("lat", ""))
        longitude = float(request.args.get("lon", ""))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid latitude and longitude are required."}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"error": "Location coordinates are out of range."}), 400

    params = urlencode({
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,weather_code,wind_speed_10m"
        ),
        "hourly": "precipitation_probability",
        "forecast_days": 1,
        "timezone": "auto"
    })
    url = "https://api.open-meteo.com/v1/forecast?" + params

    try:
        req = Request(url, headers={"User-Agent": "ProjectAETHER/1.0"})
        with urlopen(req, timeout=12) as response:
            result = json.loads(response.read().decode("utf-8"))

        current = result.get("current", {})
        hourly = result.get("hourly", {})
        rain_values = hourly.get("precipitation_probability", [])
        rain_chance = rain_values[0] if rain_values else None

        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            80: "Rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Thunderstorm with heavy hail"
        }

        code = current.get("weather_code")
        return jsonify({
            "status": "success",
            "current": {
                "temperature_c": current.get("temperature_2m"),
                "feels_like_c": current.get("apparent_temperature"),
                "humidity_percent": current.get("relative_humidity_2m"),
                "wind_kph": current.get("wind_speed_10m"),
                "condition": weather_codes.get(code, "Weather conditions unavailable")
            },
            "rain_chance_percent": rain_chance,
            "updated_at": current.get("time"),