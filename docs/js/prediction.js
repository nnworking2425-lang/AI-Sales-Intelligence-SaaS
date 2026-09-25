const PREDICTION_STORAGE_KEY = "ai-sales-last-prediction";

function clearStalePredictionCache() {
    const raw = localStorage.getItem(PREDICTION_STORAGE_KEY);
    if (!raw) return;

    try {
        const saved = JSON.parse(raw);
        const prediction = Number(saved.predictionValue ?? saved.prediction ?? saved.predicted_revenue ?? saved.value);
        const staleValues = new Set([273, 278, 0]);
        if (Number.isFinite(prediction) && staleValues.has(prediction)) {
            localStorage.removeItem(PREDICTION_STORAGE_KEY);
        }
    } catch (error) {
        console.warn("Unable to inspect saved prediction cache:", error);
    }
}

function notifyDashboardRefresh() {
    const timestamp = Date.now();
    localStorage.setItem("ai-sales-dashboard-refresh", String(timestamp));
    window.dispatchEvent(new CustomEvent("dashboard:refresh", { detail: { timestamp } }));
}

function savePredictionState(data) {
    const prediction = Number(data.predictionValue ?? data.prediction ?? data.predicted_revenue ?? data.value);
    if (!Number.isFinite(prediction)) return;
    localStorage.setItem(PREDICTION_STORAGE_KEY, JSON.stringify({
        predictionValue: prediction,
        modelName: data.modelName || "RandomForestRegressor",
        accuracy: data.accuracy || "91.53%",
        timestamp: data.timestamp || formatTimestamp(new Date())
    }));
}

function restorePredictionState() {
    const raw = localStorage.getItem(PREDICTION_STORAGE_KEY);
    if (!raw) return;

    try {
        const saved = JSON.parse(raw);
        const prediction = Number(saved.predictionValue ?? saved.prediction ?? saved.predicted_revenue ?? saved.value);
        if (!Number.isFinite(prediction)) return;

        displayPrediction({
            predictionValue: prediction,
            modelName: saved.modelName || "RandomForestRegressor",
            accuracy: saved.accuracy || "91.53%",
            timestamp: saved.timestamp || formatTimestamp(new Date())
        }, false);
    } catch (error) {
        console.warn("Unable to restore saved prediction:", error);
    }
}

function displayPrediction(data, shouldPersist = true) {
    const predictionResult = document.getElementById("predictionResult");
    console.log("Result container", predictionResult);
    if (!predictionResult) return;
    const prediction = Number(data.predictionValue ?? data.prediction ?? data.predicted_revenue ?? data.value);
    if (!Number.isFinite(prediction)) return;
    predictionResult.innerHTML = `<div class="prediction-success"><h3>Predicted Revenue</h3><h1 class="result-value success">${prediction.toFixed(2)}</h1></div>`;
    const status = document.getElementById("prediction-status");
    if (status) status.textContent = "Prediction Result";
    const metadata = document.getElementById("prediction-metadata");
    if (metadata) metadata.hidden = false;
    const timestamp = document.getElementById("prediction-timestamp");
    if (timestamp) timestamp.textContent = data.timestamp || "--";
    const model = document.getElementById("prediction-model");
    if (model) model.textContent = data.modelName || "RandomForestRegressor";
    const accuracy = document.getElementById("prediction-accuracy");
    if (accuracy) accuracy.textContent = data.accuracy || "91.53%";

    if (shouldPersist) {
        savePredictionState(data);
        notifyDashboardRefresh();
    }
    console.log("Prediction UI updated");
}

function getPredictionInputValue(fieldName) {
    const aliases = {
        OrderCount: ["OrderCount", "orderCount", "order_count"],
        QuantitySold: ["QuantitySold", "quantitySold", "quantity_sold"],
        Revenue_Lag1: ["Revenue_Lag1", "revenueLag1", "revenue_lag1"],
        Revenue_Lag2: ["Revenue_Lag2", "revenueLag2", "revenue_lag2"],
        Revenue_Lag3: ["Revenue_Lag3", "revenueLag3", "revenue_lag3"],
        Quantity_Lag1: ["Quantity_Lag1", "quantityLag1", "quantity_lag1"]
    };

    const candidates = aliases[fieldName] || [fieldName];
    for (const candidate of candidates) {
        const element = document.getElementById(candidate);
        if (element && element.value !== "") {
            return Number(element.value);
        }
    }
    return 0;
}

async function predict() {
    console.log("START PREDICT");
    const result = document.getElementById("predictionResult");
    const status = document.getElementById("prediction-status");
    if (!result) return;
    const payload = {
        OrderCount: getPredictionInputValue("OrderCount"),
        QuantitySold: getPredictionInputValue("QuantitySold"),
        Revenue_Lag1: getPredictionInputValue("Revenue_Lag1"),
        Revenue_Lag2: getPredictionInputValue("Revenue_Lag2"),
        Revenue_Lag3: getPredictionInputValue("Revenue_Lag3"),
        Quantity_Lag1: getPredictionInputValue("Quantity_Lag1")
    };
    result.innerHTML = "<strong class=\"result-value\">Predicting...</strong>";
    if (status) status.textContent = "Requesting forecast...";
    const requestUrl = `${API_BASE_URL}/predict`;
    console.log("FETCH URL", requestUrl);
    console.log("Request URL:", requestUrl);
    console.log("PAYLOAD:", payload);

    try {
        const response = await fetch(`${API_BASE_URL}/predict`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await response.json().catch(() => ({}));
        console.log("PREDICT RESULT", data);
        console.log("PREDICT RESPONSE", data);

        if (!response.ok) {
            const errorMessage = typeof data.error === "string" ? data.error : "Prediction request failed";
            throw new Error(errorMessage.includes("Model is not available in this deployment") ? "Prediction request failed" : errorMessage);
        }

        const prediction = Number(data.predicted_revenue ?? data.prediction ?? data.predictionValue ?? data.value);
        if (!Number.isFinite(prediction)) throw new Error("The API returned an invalid prediction");
        console.log("Prediction received", data);
        const predictionState = {
            predictionValue: prediction,
            modelName: "RandomForestRegressor",
            accuracy: "91.53%",
            timestamp: formatTimestamp(new Date()),
            inputValues: payload
        };
        displayPrediction(predictionState, true);
        console.log("UPDATED UI:", document.getElementById("predictionResult"));
    } catch (error) {
        console.error("PREDICT ERROR:", error);
        result.innerHTML = "<strong class=\"result-value\">Prediction unavailable</strong>";
        if (status) status.textContent = error.message || "Prediction request failed";
    }
}

function resetPredictionPlaceholder() {
    const result = document.getElementById("predictionResult");
    const status = document.getElementById("prediction-status");
    if (result && result.textContent && result.textContent.includes("Ready for a new prediction")) {
        result.innerHTML = "<strong class=\"result-value\">Ready for a new prediction</strong>";
    }
    if (status) status.textContent = "Ready for a new prediction";
}

document.addEventListener("DOMContentLoaded", () => {
    clearStalePredictionCache();
    resetPredictionPlaceholder();
    restorePredictionState();
});
window.predict = predict;

function formatTimestamp(date) {
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}


