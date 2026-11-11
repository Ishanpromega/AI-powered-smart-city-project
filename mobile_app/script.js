const chat = document.getElementById("chat");
const commandInput = document.getElementById("command");
const voiceSelect = document.getElementById("voiceSelect");
const speechRate = document.getElementById("speechRate");
const rateValue = document.getElementById("rateValue");

let availableVoices = [];
let recognition = null;
let isListening = false;

// Add messages safely and preserve line breaks.
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

// Load the voices supplied by the current phone/browser.
function loadVoices() {
    if (!("speechSynthesis" in window)) {
        voiceSelect.innerHTML = '<option value="">Speech is not supported</option>';
        return;
    }

    availableVoices = speechSynthesis.getVoices();
    const previousVoice = voiceSelect.value;

    voiceSelect.innerHTML = "";

    if (availableVoices.length === 0) {
        voiceSelect.innerHTML = '<option value="">Default device voice</option>';
        return;
    }

    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = "Default device voice";
    voiceSelect.appendChild(defaultOption);

    availableVoices.forEach((voice, index) => {
        const option = document.createElement("option");
        option.value = voice.voiceURI;
        option.textContent = `${voice.name} (${voice.lang})`;
        voiceSelect.appendChild(option);
    });

    if (availableVoices.some(voice => voice.voiceURI === previousVoice)) {
        voiceSelect.value = previousVoice;
    }
}

if ("speechSynthesis" in window) {
    loadVoices();
    speechSynthesis.addEventListener?.("voiceschanged", loadVoices);
    // Compatibility fallback for browsers that expose the event on the window.
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

// Send typed or recognised speech to the existing Flask AI endpoint.
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
        const response = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message })
        });

        const data = await response.json();
        thinking.remove();

        if (!response.ok) {
            throw new Error(data.error || "AI connection failed.");
        }

        reply(data.reply || "I couldn't generate a reply.");
    } catch (error) {
        thinking.remove();
        // Avoid speaking technical error details aloud.
        addMessage("AETHER: ", "I couldn't connect to the AI service. Please try again.");
        console.error(error);
    }
}

// Voice input: the browser converts speech into text, then sends it to AETHER.
function startVoice() {
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        addMessage("AETHER: ", "Voice input is not supported by this browser. Try Chrome.");
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
        document.getElementById("voiceButton").textContent = "🎙️ LISTENING... TAP TO STOP";
        addMessage("AETHER: ", "I'm listening. Speak now.");
    };

    recognition.onresult = function(event) {
        const transcript = event.results[0][0].transcript;
        commandInput.value = transcript;
        sendCommand();
    };

    recognition.onerror = function(event) {
        console.warn("Speech recognition error:", event.error);
        if (event.error !== "no-speech" && event.error !== "aborted") {
            addMessage("AETHER: ", "I couldn't hear that clearly. Please try again.");
        }
    };

    recognition.onend = function() {
        isListening = false;
        document.getElementById("voiceButton").textContent = "🎙️ SPEAK TO AETHER";
    };

    try {
        recognition.start();
    } catch (error) {
        isListening = false;
        document.getElementById("voiceButton").textContent = "🎙️ SPEAK TO AETHER";
        console.error(error);
    }
}

function webSearch() {
    const searchInput = document.getElementById("searchQuery");
    const query = searchInput.value.trim();

    if (!query) {
        reply("Please enter something to search for.");
        return;
    }

    commandInput.value = "Search the web for: " + query;
    searchInput.value = "";
    sendCommand();
}

// UI events
document.getElementById("sendButton").addEventListener("click", sendCommand);
document.getElementById("voiceButton").addEventListener("click", startVoice);
document.getElementById("searchButton").addEventListener("click", webSearch);

commandInput.addEventListener("keydown", event => {
    if (event.key === "Enter") sendCommand();
});

document.getElementById("searchQuery").addEventListener("keydown", event => {
    if (event.key === "Enter") webSearch();
});

speechRate.addEventListener("input", () => {
    rateValue.textContent = Number(speechRate.value).toFixed(1) + "x";
});

document.getElementById("testVoiceButton").addEventListener("click", () => {
    speakMessage("Hello! I am AETHER. How can I help you today?");
});

document.getElementById("stopSpeechButton").addEventListener("click", () => {
    if ("speechSynthesis" in window) speechSynthesis.cancel();
});
