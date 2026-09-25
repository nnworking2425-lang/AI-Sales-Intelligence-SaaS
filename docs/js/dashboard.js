const API_BASE = "https://ai-sales-intelligence-saas.onrender.com";
const DASHBOARD_REFRESH_KEY = "ai-sales-dashboard-refresh";

function setTextForIds(ids, value) {
    const uniqueIds = [...new Set((ids || []).filter(Boolean))];
    uniqueIds.forEach((id) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    });
}

function safeNumber(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function formatMetric(value, digits = 2, suffix = "") {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
    const formatted = Number(value).toFixed(digits);
    return `${formatted}${suffix}`;
}

async function getJson(path, options = {}) {
    const url = `${API_BASE}${path}`;
    try {
        const response = await fetch(url, { credentials: "include", ...options });
        const text = await response.text();
        let payload = {};

        if (text) {
            try {
                payload = JSON.parse(text);
            } catch (error) {
                console.error(`Invalid JSON from ${url}:`, error);
                payload = {};
            }
        }

        if (!response.ok) {
            throw new Error(payload.error || payload.message || `Request failed: ${response.status}`);
        }

        return payload;
    } catch (error) {
        console.error(`Dashboard API request failed for ${path}:`, error);
        throw error;
    }
}

async function requireUser() {
    const result = await getJson("/current-user");
    if (!result.user) {
        window.location.href = "../login.html";
        return null;
    }
    document.querySelectorAll("[data-user-name]").forEach((element) => { element.textContent = result.user.username; });
    document.querySelectorAll("[data-user-role]").forEach((element) => { element.textContent = result.user.role; });
    document.querySelectorAll("[data-user-initials]").forEach((element) => { element.textContent = result.user.username.slice(0, 2).toUpperCase(); });
    return result.user;
}

async function logout() {
    await getJson("/logout", { method: "POST" });
    window.location.href = "../login.html";
}

function setActiveNav() {
    const page = location.pathname.split("/").pop() || "dashboard.html";
    const canonicalPages = { "model.html": "training.html", "business.html": "powerbi.html" };
    document.querySelectorAll("[data-nav-page]").forEach((link) => {
        const target = link.getAttribute("data-nav-page");
        if (canonicalPages[target]) {
            link.setAttribute("data-nav-page", canonicalPages[target]);
            link.setAttribute("href", canonicalPages[target]);
        }
        link.classList.toggle("active", (canonicalPages[page] || page) === link.getAttribute("data-nav-page"));
    });
}

async function loadPerformance() {
    try {
        const performance = await getJson("/api/dashboard");
        const r2Value = safeNumber(performance.r2, 0) * 100;
        const maeValue = safeNumber(performance.mae, 0);
        const rmseValue = safeNumber(performance.rmse, 0);
        const sampleValue = safeNumber(performance.samples, 0);

        setTextForIds(["kpi-r2", "performance-r2", "analytics-accuracy"], `${r2Value.toFixed(2)}%`);
        setTextForIds(["kpi-mae", "performance-mae"], formatMetric(maeValue, 2));
        setTextForIds(["kpi-rmse", "performance-rmse"], formatMetric(rmseValue, 2));
        setTextForIds(["kpi-samples", "performance-samples"], formatMetric(sampleValue, 0));
    } catch (error) { console.error("Performance error:", error); }
}

async function loadAnalyticsSummary() {
    try {
        const data = await getJson("/api/analytics");
        setTextForIds(["analytics-total", "total-predictions"], formatMetric(safeNumber(data.total_revenue, 0), 2));
        setTextForIds(["analytics-average", "average-prediction"], formatMetric(safeNumber(data.average_order_value ?? data.average_revenue, 0), 2));
        setTextForIds(["analytics-growth"], `${safeNumber(data.growth ?? data.growth_rate, 0).toFixed(2)}%`);
        setTextForIds(["analytics-best-day"], data.best_sales_day || "--");
        setTextForIds(["analytics-highest", "highest-forecast"], formatMetric(safeNumber(data.highest_revenue, 0), 2));
    } catch (error) { console.error("Analytics error:", error); }
}

async function loadAnalyticsCharts() {
    try {
        const trends = await getJson("/sales-trends");
        ["daily", "weekly", "monthly"].forEach((period) => {
            const canvas = document.getElementById(`${period}-chart`);
            if (!canvas || typeof Chart === "undefined") return;
            new Chart(canvas, {
                type: "line",
                data: {
                    labels: trends[period].map((item) => item.label),
                    datasets: [{ label: `${period[0].toUpperCase()}${period.slice(1)} Revenue`, data: trends[period].map((item) => Number(item.revenue)), borderColor: "#3454d1", backgroundColor: "rgba(52,84,209,.12)", fill: true, tension: .25 }]
                },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
            });
        });
    } catch (error) { console.error("Trend error:", error); }
}

async function loadModelInfo() {
    try {
        const data = await getJson("/api/model-info");
        const modelName = data.model || "--";
        const accuracyValue = safeNumber(data.r2, 0) * 100;

        document.querySelectorAll("[data-model-name]").forEach((element) => { element.textContent = modelName; });
        document.querySelectorAll("[data-model-accuracy]").forEach((element) => { element.textContent = `${accuracyValue.toFixed(2)}%`; });
        setTextForIds(["current-model-accuracy", "analytics-accuracy"], `${accuracyValue.toFixed(2)}%`);
    } catch (error) { console.error("Model info error:", error); }
}

async function loadTrainingHistory() {
    try {
        const history = await getJson("/model-training-history");
        const body = document.getElementById("model-history-body");
        if (!body) return;
        body.innerHTML = history.length ? history.map((record) => `<tr><td>${record.created_at}</td><td>${record.model_name}</td><td>${Number(record.r2_score).toFixed(4)}</td><td>${Number(record.mae).toFixed(2)}</td><td>${Number(record.rmse).toFixed(2)}</td></tr>`).join("") : "<tr><td colspan=\"5\">No model training history</td></tr>";
    } catch (error) { console.error("Training history error:", error); }
}

async function trainNewModel() {
    const input = document.getElementById("training-file");
    const status = document.getElementById("training-status");
    if (!input?.files[0]) { status.textContent = "Select a CSV file first."; return; }
    status.textContent = "Training model...";
    const form = new FormData();
    form.append("file", input.files[0]);
    try {
        const result = await getJson("/train", { method: "POST", body: form });
        status.textContent = `${result.message} Accuracy: ${(Number(result.r2) * 100).toFixed(2)}%`;
        await Promise.all([loadModelInfo(), loadTrainingHistory(), loadPerformance()]);
    } catch (error) { status.textContent = error.message; }
}

async function loadHistory() {
    try {
        const history = await getJson("/prediction-history");
        const predictions = Array.isArray(history) ? history.map((record) => Number(record.predicted_revenue)).filter((value) => Number.isFinite(value)) : [];
        const latestForecast = predictions.length ? predictions[0].toFixed(2) : "--";
        setTextForIds(["dashboard-latest-forecast", "latest-forecast"], latestForecast);

        const body = document.getElementById("history-body");
        if (!body) {
            return;
        }

        window.predictionHistory = history;
        window.predictionHistoryPage = 1;
        renderHistoryPage();

        const canvas = document.getElementById("prediction-chart");
        if (canvas && typeof Chart !== "undefined") {
            new Chart(canvas, { type: "line", data: { labels: [...history].reverse().map((record) => record.created_at), datasets: [{ label: "Predicted Revenue", data: [...history].reverse().map((record) => Number(record.predicted_revenue)), borderColor: "#3454d1", backgroundColor: "rgba(52,84,209,.12)", fill: true, tension: .25 }] }, options: { responsive: true, maintainAspectRatio: false } });
        }
    } catch (error) { console.error("History error:", error); }
}

function renderHistoryPage() {
    const body = document.getElementById("history-body");
    if (!body) return;
    const records = window.predictionHistory || [];
    const pageSize = 10;
    const totalPages = Math.max(1, Math.ceil(records.length / pageSize));
    const page = Math.min(window.predictionHistoryPage || 1, totalPages);
    window.predictionHistoryPage = page;
    const start = (page - 1) * pageSize;
    body.innerHTML = records.length ? records.slice(start, start + pageSize).map((record) => `<tr><td>${record.created_at}</td><td>${record.order_count}</td><td>${Number(record.actual_revenue).toFixed(2)}</td><td>${Number(record.predicted_revenue).toFixed(2)}</td></tr>`).join("") : "<tr><td colspan=\"4\">No prediction history</td></tr>";
    const status = document.getElementById("page-status");
    if (status) status.textContent = `Page ${page} of ${totalPages}`;
    const previous = document.getElementById("previous-page");
    const next = document.getElementById("next-page");
    if (previous) previous.disabled = page === 1;
    if (next) next.disabled = page === totalPages;
}

function exportHistory() {
    const records = window.predictionHistory || [];
    const rows = [["Date", "Order Count", "Actual Revenue", "AI Prediction"], ...records.map((record) => [record.created_at, record.order_count, record.actual_revenue, record.predicted_revenue])];
    const csv = rows.map((row) => row.map((value) => `"${String(value ?? "").replaceAll("\"", "\"\"")}"`).join(",")).join("\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    link.download = "prediction_history.csv";
    link.click();
    URL.revokeObjectURL(link.href);
}

async function refreshDashboardState() {
    await Promise.all([
        loadPerformance(),
        loadAnalyticsSummary(),
        loadModelInfo(),
        loadTrainingHistory(),
        loadHistory(),
        loadAnalyticsCharts()
    ]);
}

window.addEventListener("dashboard:refresh", () => {
    refreshDashboardState();
});

window.addEventListener("storage", (event) => {
    if (event.key === DASHBOARD_REFRESH_KEY) {
        refreshDashboardState();
    }
});

document.addEventListener("DOMContentLoaded", async () => {
    setActiveNav();
    const user = await requireUser();
    if (!user) return;
    document.getElementById("logout-button")?.addEventListener("click", logout);
    document.getElementById("train-model")?.addEventListener("click", trainNewModel);
    document.getElementById("export-history")?.addEventListener("click", exportHistory);
    document.getElementById("previous-page")?.addEventListener("click", () => { window.predictionHistoryPage--; renderHistoryPage(); });
    document.getElementById("next-page")?.addEventListener("click", () => { window.predictionHistoryPage++; renderHistoryPage(); });
    refreshDashboardState();
});
