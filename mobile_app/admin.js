
const loginSection = document.getElementById("loginSection");
const dashboardSection = document.getElementById("dashboardSection");

const loginForm = document.getElementById("loginForm");
const passwordInput = document.getElementById("adminPassword");
const loginButton = document.getElementById("loginButton");
const loginError = document.getElementById("loginError");

const refreshButton = document.getElementById("refreshButton");
const clearAnalyticsButton =
    document.getElementById("clearAnalyticsButton");
const logoutButton = document.getElementById("logoutButton");

const dashboardError = document.getElementById("dashboardError");


/* --------------------------------
   PAGE DISPLAY
-------------------------------- */

function showLogin() {
    loginSection.hidden = false;
    dashboardSection.hidden = true;
}

function showDashboard() {
    loginSection.hidden = true;
    dashboardSection.hidden = false;
}

function showDashboardError(message) {
    dashboardError.textContent = message;
    dashboardError.hidden = false;
}


/* --------------------------------
   LOAD ANALYTICS
-------------------------------- */

async function loadAnalytics() {

    refreshButton.disabled = true;
    dashboardError.hidden = true;

    try {

        const response = await fetch("/api/analytics", {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        const data = await response.json();

        if (response.status === 401) {
            showLogin();
            return;
        }

        if (!response.ok || data.status !== "success") {
            throw new Error(
                data.error || "Analytics unavailable."
            );
        }

        document.getElementById("totalQuestions").textContent =
            data.total_questions ?? 0;

        document.getElementById("totalVisitors").textContent =
            data.total_visitors ?? 0;

        document.getElementById("totalTopics").textContent =
            data.total_topics ?? 0;

        const popular = data.most_popular_topic;

        document.getElementById("popularTopic").textContent =
            popular ? popular.topic : "None";

        document.getElementById("popularCount").textContent =
            popular
                ? `${popular.questions} questions recorded`
                : "No data yet";

        renderTopics(data.topics || []);

        document.getElementById("lastUpdated").textContent =
            "Updated: " + new Date().toLocaleTimeString();

    } catch (error) {

        showDashboardError(
            error.message || "Could not connect to AETHER."
        );

    } finally {

        refreshButton.disabled = false;

    }
}


/* --------------------------------
   RENDER TOPIC ANALYTICS
-------------------------------- */

function renderTopics(topics) {

    const container = document.getElementById("topicsList");

    container.replaceChildren();

    if (!topics.length) {

        const empty = document.createElement("p");

        empty.className = "muted";
        empty.textContent =
            "No question analytics recorded yet.";

        container.appendChild(empty);

        return;
    }

    const maximum = Math.max(
        ...topics.map(topic => Number(topic.questions) || 0),
        1
    );

    topics.forEach(topic => {

        const count = Number(topic.questions) || 0;

        const row = document.createElement("div");
        row.className = "topic-row";

        const name = document.createElement("div");
        name.className = "topic-name";
        name.textContent = topic.topic;

        const track = document.createElement("div");
        track.className = "bar-track";

        const fill = document.createElement("div");
        fill.className = "bar-fill";

        fill.style.width =
            `${(count / maximum) * 100}%`;

        track.appendChild(fill);

        const countLabel = document.createElement("div");
        countLabel.className = "topic-count";
        countLabel.textContent = count;

        row.append(name, track, countLabel);

        container.appendChild(row);

    });
}


/* --------------------------------
   ADMIN LOGIN
-------------------------------- */

loginForm.addEventListener("submit", async event => {

    event.preventDefault();

    loginButton.disabled = true;
    loginError.textContent = "";

    try {

        const response = await fetch("/api/admin/login", {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                password: passwordInput.value
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(
                data.error || "Login failed."
            );
        }

        passwordInput.value = "";

        showDashboard();

        await loadAnalytics();

    } catch (error) {

        loginError.textContent =
            error.message || "Could not connect to AETHER.";

    } finally {

        loginButton.disabled = false;

    }

});


/* --------------------------------
   REFRESH ANALYTICS
-------------------------------- */

refreshButton.addEventListener("click", () => {
    loadAnalytics();
});


/* --------------------------------
   CLEAR ANALYTICS
-------------------------------- */

clearAnalyticsButton.addEventListener(
    "click",
    async () => {

        const confirmed = confirm(
            "CLEAR ALL QUESTION ANALYTICS?\n\n" +
            "This will delete recorded topic counts.\n\n" +
            "Visitor sessions and conversations will NOT be deleted.\n\n" +
            "This action cannot be undone."
        );

        if (!confirmed) {
            return;
        }

        clearAnalyticsButton.disabled = true;
        refreshButton.disabled = true;

        dashboardError.hidden = true;

        try {

            const response = await fetch(
                "/api/admin/analytics/clear",
                {
                    method: "POST",
                    credentials: "same-origin",
                    cache: "no-store"
                }
            );

            const data = await response.json();

            if (response.status === 401) {

                showLogin();

                throw new Error(
                    "Your admin session expired. Please log in again."
                );
            }

            if (!response.ok || data.status !== "success") {

                throw new Error(
                    data.error || "Could not clear analytics."
                );
            }

            await loadAnalytics();

            alert(
                "AETHER analytics cleared successfully!\n\n" +
                "Deleted topic records: " +
                data.deleted_topics
            );

        } catch (error) {

            showDashboardError(
                error.message || "Could not clear analytics."
            );

        } finally {

            clearAnalyticsButton.disabled = false;
            refreshButton.disabled = false;

        }

    }
);


/* --------------------------------
   ADMIN LOGOUT
-------------------------------- */

logoutButton.addEventListener("click", async () => {

    logoutButton.disabled = true;

    try {

        const response = await fetch("/api/admin/logout", {
            method: "POST",
            credentials: "same-origin"
        });

        if (!response.ok) {
            throw new Error(
                "Logout failed. Please try again."
            );
        }

        showLogin();

        passwordInput.value = "";
        loginError.textContent = "";

    } catch (error) {

        showDashboardError(error.message);

    } finally {

        logoutButton.disabled = false;

    }

});


/* --------------------------------
   RESTORE ADMIN SESSION
-------------------------------- */

async function initializeAdmin() {

    try {

        const response = await fetch("/api/analytics", {
            credentials: "same-origin",
            cache: "no-store"
        });

        if (response.ok) {

            showDashboard();

            await loadAnalytics();

        } else {

            showLogin();

        }

    } catch {

        showLogin();

    }

}

initializeAdmin();
