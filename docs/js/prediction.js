const API_BASE_URL = "https://ai-sales-intelligence-saas.onrender.com";

const PREDICTION_STORAGE_KEY = "ai-sales-last-prediction";

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
    predictionResult.innerHTML = `<div class="prediction-success"><h3>Forecast Result</h3><h1 class="result-value success">$${prediction.toFixed(2)}</h1><p>AI Predicted Revenue</p></div>`;
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

async function predict() {
    console.log("START PREDICT");
    const result = document.getElementById("predictionResult");
    const status = document.getElementById("prediction-status");
    if (!result) return;
    const data = {
        OrderCount: Number(document.getElementById("orderCount").value),
        QuantitySold: Number(document.getElementById("quantitySold").value),
        Revenue_Lag1: Number(document.getElementById("revenueLag1").value),
        Revenue_Lag2: Number(document.getElementById("revenueLag2").value),
        Revenue_Lag3: Number(document.getElementById("revenueLag3").value),
        Quantity_Lag1: Number(document.getElementById("quantityLag1").value)
    };
    result.innerHTML = "<strong class=\"result-value\">Predicting...</strong>";
    if (status) status.textContent = "Requesting forecast...";
    console.log("Request URL:", `${API_BASE_URL}/predict`);
    console.log("PAYLOAD:", data);

    try {
        const response = await fetch(`${API_BASE_URL}/predict`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data)
        });

        const rawText = await response.text();
        let resultPayload = {};
        if (rawText) {
            try {
                resultPayload = JSON.parse(rawText);
            } catch (error) {
                console.error("Prediction JSON parse error:", error);
                resultPayload = {};
            }
        }

        console.log("API RESPONSE:", resultPayload);
        if (!response.ok) {
            const errorMessage = typeof resultPayload.error === "string" ? resultPayload.error : "Prediction request failed";
            throw new Error(errorMessage.includes("Model is not available in this deployment") ? "Prediction request failed" : errorMessage);
        }

        const prediction = Number(resultPayload.prediction ?? resultPayload.predicted_revenue ?? resultPayload.value);
        if (!Number.isFinite(prediction)) throw new Error("The API returned an invalid prediction");
        console.log("Prediction received", resultPayload);
        const predictionState = {
            predictionValue: prediction,
            modelName: "RandomForestRegressor",
            accuracy: "91.53%",
            timestamp: formatTimestamp(new Date()),
            inputValues: data
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
    resetPredictionPlaceholder();
    restorePredictionState();
});
window.predict = predict;

function formatTimestamp(date) {
    const pad = (value) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}


