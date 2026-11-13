
const chat = document.getElementById("chat");
const commandInput = document.getElementById("command");
const voiceSelect = document.getElementById("voiceSelect");
const speechRate = document.getElementById("speechRate");
const rateValue = document.getElementById("rateValue");

let availableVoices = [];
let recognition = null;
let isListening = false;

// ==========================================
// AETHER VISITOR SESSION
// ==========================================

const SESSION_KEY = "aether_session_id";

let aetherSessionId = null;

async function initializeSession() {

    let savedSessionId = null;

    try {
        savedSessionId = localStorage.getItem(SESSION_KEY);
    } catch (error) {
        console.warn("AETHER: Browser storage unavailable.");
    }

    async function createOrRestoreSession(sessionId) {

        const response = await fetch("/api/session/start", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(
                sessionId ? { session_id: sessionId } : {}
            )
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Session initialization failed."
            );
        }

        if (!data.session_id) {
            throw new Error("Server did not return a session ID.");
        }

        return data.session_id;
    }

    try {

        // Try restoring the previous visitor session.
        try {

            aetherSessionId = await createOrRestoreSession(
                savedSessionId
            );

        } catch (error) {

            // If the saved ID is invalid, request a fresh session.
            if (!savedSessionId) {
                throw error;
            }

            console.warn(
                "AETHER: Previous session could not be restored. Creating a new one."
            );

            aetherSessionId = await createOrRestoreSession(null);
        }

        try {
            localStorage.setItem(
                SESSION_KEY,
                aetherSessionId
            );
        } catch (error) {
            console.warn("AETHER: Could not save session locally.");
        }

        console.log(
            "AETHER visitor session ready:",
            aetherSessionId
        );

        return true;

    } catch (error) {

        aetherSessionId = null;

        console.error(
            "AETHER session error:",
            error
        );

        return false;
    }
}

// Start session as soon as the dashboard loads.
const sessionReady = initializeSession();


// ==========================================
// AI CHAT
// ==========================================

function addMessage(label, message) {
    const element = document.createElement("div");
    element.textContent = label + message;
    element.style.whiteSpace = "pre-wrap";
    element.style.marginBottom = "18px";

    chat.appendChild(element);
    chat.scrollTop = chat.scrollHeight;
}

function cleanForSpeech(message) {
    return message
        .replace(/```[\s\S]*?```/g, "Code omitted.")
        .replace(/https?:\/\/\S+/g, "link")
        .replace(/[*_#`~]/g, "")
        .replace(/[^\w\s.,!?'-]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}


// ==========================================
// VOICE OUTPUT
// ==========================================

function loadVoices() {

    if (!("speechSynthesis" in window)) {
        voiceSelect.innerHTML =
            '<option value="">Speech is not supported</option>';
        return;
    }

    availableVoices = speechSynthesis.getVoices();

    const previousVoice = voiceSelect.value;
    voiceSelect.innerHTML = "";

    if (availableVoices.length === 0) {
        voiceSelect.innerHTML =
            '<option value="">Default device voice</option>';
        return;
    }

    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = "Default device voice";
    voiceSelect.appendChild(defaultOption);

    availableVoices.forEach(voice => {

        const option = document.createElement("option");

        option.value = voice.voiceURI;
        option.textContent = `${voice.name} (${voice.lang})`;

        voiceSelect.appendChild(option);
    });

    if (availableVoices.some(
        voice => voice.voiceURI === previousVoice
    )) {
        voiceSelect.value = previousVoice;
    }
}

if ("speechSynthesis" in window) {

    loadVoices();

    speechSynthesis.addEventListener?.(
        "voiceschanged",
        loadVoices
    );

    window.speechSynthesis.onvoiceschanged = loadVoices;
}

function speakMessage(message) {

    if (!("speechSynthesis" in window)) return;

    speechSynthesis.cancel();

    const text = cleanForSpeech(message);

    if (!text) return;

    const speech = new SpeechSynthesisUtterance(text);

    const selectedVoice = availableVoices.find(
        voice => voice.voiceURI === voiceSelect.value
    );

    if (selectedVoice) {
        speech.voice = selectedVoice;
    }

    speech.rate = Number(speechRate.value) || 0.9;
    speech.pitch = 1;
    speech.lang = selectedVoice?.lang || "en-IN";

    speechSynthesis.speak(speech);
}

function reply(message) {
    addMessage("AETHER: ", message);
    speakMessage(message);
}


// ==========================================
// AI COMMUNICATION
// ==========================================

async function sendCommand() {

    const message = commandInput.value.trim();

    if (!message) return;

    addMessage("YOU: ", message);
    commandInput.value = "";

    const thinking = document.createElement("div");

    thinking.textContent = "AETHER: Thinking...";
    thinking.style.marginBottom = "18px";

    chat.appendChild(thinking);
    chat.scrollTop = chat.scrollHeight;

    try {

        // Wait for the visitor session initialization.
        await sessionReady;

        const response = await fetch("/api/chat", {

            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message,
                session_id: aetherSessionId
            })
        });

        const data = await response.json();

        thinking.remove();

        if (!response.ok) {
            throw new Error(
                data.error || data.reply || "AI connection failed."
            );
        }

        reply(
            data.reply || "I couldn't generate a reply."
        );

    } catch (error) {

        thinking.remove();

        addMessage(
            "AETHER: ",
            "I couldn't connect to the AI service. Please try again."
        );

        console.error(error);
    }
}


// ==========================================
// VOICE INPUT
// ==========================================

function startVoice() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!SpeechRecognition) {

        addMessage(
            "AETHER: ",
            "Voice input is not supported by this browser. Try Chrome."
        );

        return;
    }

    if (isListening && recognition) {
        recognition.stop();
        return;
    }

    if ("speechSynthesis" in window) {
        speechSynthesis.cancel();
    }

    recognition = new SpeechRecognition();

    recognition.lang = "en-IN";
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = function() {

        isListening = true;

        document.getElementById("voiceButton").textContent =
            "🎙️ LISTENING... TAP TO STOP";

        addMessage(
            "AETHER: ",
            "I'm listening. Speak now."
        );
    };

    recognition.onresult = function(event) {

        const transcript =
            event.results[0][0].transcript;

        commandInput.value = transcript;
        sendCommand();
    };

    recognition.onerror = function(event) {

        console.warn(
            "Speech recognition error:",
            event.error
        );

        if (
            event.error !== "no-speech" &&
            event.error !== "aborted"
        ) {

            addMessage(
                "AETHER: ",
                "I couldn't hear that clearly. Please try again."
            );
        }
    };

    recognition.onend = function() {

        isListening = false;

        document.getElementById("voiceButton").textContent =
            "🎙️ SPEAK TO AETHER";
    };

    try {

        recognition.start();

    } catch (error) {

        isListening = false;

        document.getElementById("voiceButton").textContent =
            "🎙️ SPEAK TO AETHER";

        console.error(error);
    }
}


// ==========================================
// WEB SEARCH
// ==========================================

function webSearch() {

    const searchInput =
        document.getElementById("searchQuery");

    const query = searchInput.value.trim();

    if (!query) {

        reply("Please enter something to search for.");

        return;
    }

    commandInput.value =
        "Search the web for: " + query;

    searchInput.value = "";

    sendCommand();
}


// ==========================================
// EXISTING UI EVENTS
// ==========================================

document.getElementById("sendButton")
    .addEventListener("click", sendCommand);

document.getElementById("voiceButton")
    .addEventListener("click", startVoice);

document.getElementById("searchButton")
    .addEventListener("click", webSearch);

commandInput.addEventListener("keydown", event => {

    if (event.key === "Enter") {
        sendCommand();
    }
});

document.getElementById("searchQuery")
    .addEventListener("keydown", event => {

        if (event.key === "Enter") {
            webSearch();
        }
    });

speechRate.addEventListener("input", () => {

    rateValue.textContent =
        Number(speechRate.value).toFixed(1) + "x";
});

document.getElementById("testVoiceButton")
    .addEventListener("click", () => {

        speakMessage(
            "Hello! I am AETHER. How can I help you today?"
        );
    });

document.getElementById("stopSpeechButton")
    .addEventListener("click", () => {

        if ("speechSynthesis" in window) {
            speechSynthesis.cancel();
        }
    });


// ==========================================
// AETHER SETUP MODE + LOCATION
// ==========================================

(function setupAetherLocation() {

    const weatherElement =
        document.getElementById("weather");

    const weatherPanel =
        weatherElement?.closest(".panel");

    if (!weatherElement || !weatherPanel) {

        console.error(
            "AETHER: Weather panel not found."
        );

        return;
    }

    if (document.getElementById("locationSettings")) {
        return;
    }

    const LOCATION_KEY = "aether_saved_location";

    const panel = document.createElement("section");

    panel.className = "panel";
    panel.id = "locationSettings";

    panel.innerHTML = `
        <h2>LOCATION SETTINGS</h2>

        <button id="setupToggle">
            OPEN SETUP MODE
        </button>

        <div id="setupContent" hidden>

            <p>Select your city or use your current location.</p>

            <button id="currentLocation">
                USE MY CURRENT LOCATION
            </button>

            <div style="margin-top:12px;">

                <input
                    id="citySearch"
                    type="text"
                    placeholder="Enter city name"
                    style="width:100%;padding:12px;"
                >

                <button id="citySearchButton">
                    SEARCH CITY
                </button>

            </div>

            <div id="locationResults"></div>

            <p id="locationStatus" aria-live="polite"></p>

        </div>
    `;

    weatherPanel.parentNode.insertBefore(
        panel,
        weatherPanel
    );

    const toggle =
        document.getElementById("setupToggle");

    const content =
        document.getElementById("setupContent");

    const currentButton =
        document.getElementById("currentLocation");

    const searchInput =
        document.getElementById("citySearch");

    const searchButton =
        document.getElementById("citySearchButton");

    const results =
        document.getElementById("locationResults");

    const status =
        document.getElementById("locationStatus");

    let savedLocation = null;

    try {

        savedLocation = JSON.parse(
            localStorage.getItem(LOCATION_KEY)
        );

    } catch (error) {

        localStorage.removeItem(LOCATION_KEY);
    }

    toggle.addEventListener("click", () => {

        content.hidden = !content.hidden;

        toggle.textContent = content.hidden
            ? "OPEN SETUP MODE"
            : "CLOSE SETUP MODE";
    });


    // Save selected location.
    function saveLocation(name, latitude, longitude) {

        const location = {
            name: name,
            latitude: latitude,
            longitude: longitude
        };

        savedLocation = location;

        localStorage.setItem(
            LOCATION_KEY,
            JSON.stringify(location)
        );

        status.textContent =
            "Location saved successfully!";

        results.replaceChildren();

        loadWeather(location);
    }


    // Search for a city.
    async function searchCity() {

        const city = searchInput.value.trim();

        if (!city) {

            status.textContent =
                "Please enter a city name.";

            return;
        }

        status.textContent = "Searching...";

        results.replaceChildren();

        try {

            const url =
                "https://geocoding-api.open-meteo.com/v1/search?name=" +
                encodeURIComponent(city) +
                "&count=5&language=en&format=json";

            const response = await fetch(url);

            if (!response.ok) {
                throw new Error("Search unavailable.");
            }

            const data = await response.json();

            if (!data.results?.length) {

                status.textContent =
                    "No matching city found.";

                return;
            }

            status.textContent =
                "Choose your location:";

            data.results.forEach(place => {

                const button =
                    document.createElement("button");

                button.textContent = [
                    place.name,
                    place.admin1,
                    place.country
                ].filter(Boolean).join(", ");

                button.style.display = "block";
                button.style.margin = "8px 0";
                button.style.padding = "10px";

                button.addEventListener("click", () => {

                    saveLocation(
                        button.textContent,
                        place.latitude,
                        place.longitude
                    );
                });

                results.appendChild(button);
            });

        } catch (error) {

            status.textContent =
                "City search failed. Try again.";

            console.error(
                "AETHER location search:",
                error
            );
        }
    }

    searchButton.addEventListener(
        "click",
        searchCity
    );

    searchInput.addEventListener("keydown", event => {

        if (event.key === "Enter") {
            searchCity();
        }
    });


    // Detect current location.
    currentButton.addEventListener("click", () => {

        if (!navigator.geolocation) {

            status.textContent =
                "Location is not supported by this browser.";

            return;
        }

        status.textContent =
            "Requesting location permission...";

        navigator.geolocation.getCurrentPosition(

            position => {

                saveLocation(
                    "Current location",
                    position.coords.latitude,
                    position.coords.longitude
                );
            },

            error => {

                status.textContent =
                    error.code === 1
                        ? "Location permission denied. Search for your city instead."
                        : "Unable to get location. Please try city search.";
            },

            {
                enableHighAccuracy: false,
                timeout: 15000,
                maximumAge: 300000
            }
        );
    });


    // Weather descriptions.
    function weatherDescription(code) {

        const descriptions = {
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
            82: "Heavy rain showers",
            95: "Thunderstorm"
        };

        return descriptions[code] ||
            "Weather conditions unavailable";
    }


    // Fetch current weather from Open-Meteo.
    async function loadWeather(location) {

        weatherElement.style.whiteSpace = "pre-line";

        weatherElement.textContent =
            "Loading weather...";

        try {

            const url =
                "https://api.open-meteo.com/v1/forecast" +
                "?latitude=" + location.latitude +
                "&longitude=" + location.longitude +
                "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m" +
                "&timezone=auto";

            const response = await fetch(url);

            if (!response.ok) {

                throw new Error(
                    "Weather service unavailable."
                );
            }

            const data = await response.json();

            const current = data.current;

            if (!current) {

                throw new Error(
                    "Weather data unavailable."
                );
            }

            weatherElement.textContent =

                location.name + "\n" +

                weatherDescription(
                    current.weather_code
                ) + "\n" +

                "Temperature: " +
                current.temperature_2m + " °C\n" +

                "Feels like: " +
                current.apparent_temperature + " °C\n" +

                "Humidity: " +
                current.relative_humidity_2m + "%\n" +

                "Wind: " +
                current.wind_speed_10m + " km/h";

        } catch (error) {

            weatherElement.textContent =
                "Weather unavailable. Please try again later.";

            console.error(
                "AETHER weather:",
                error
            );
        }
    }


    // Restore previously saved location.
    if (
        savedLocation &&
        Number.isFinite(savedLocation.latitude) &&
        Number.isFinite(savedLocation.longitude)
    ) {

        loadWeather(savedLocation);

    } else {

        weatherElement.textContent =
            "Please select your location in Setup Mode.";
    }

    console.log(
        "AETHER: Setup Mode initialized."
    );

})();
