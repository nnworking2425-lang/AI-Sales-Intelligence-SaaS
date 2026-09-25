async function predict() {
	const resultElement = document.getElementById("result");
	const predictButton = document.getElementById("predictButton");
	if (!resultElement) return;
	const data = {
		OrderCount: document.getElementById("OrderCount").value,
		QuantitySold: document.getElementById("QuantitySold").value,
		Revenue_Lag1: document.getElementById("Revenue_Lag1").value,
		Revenue_Lag2: document.getElementById("Revenue_Lag2").value,
		Revenue_Lag3: document.getElementById("Revenue_Lag3").value,
		Quantity_Lag1: document.getElementById("Quantity_Lag1").value
	};
	savePredictionInputs();
	const startedAt = performance.now();
	if (predictButton) {
		predictButton.disabled = true;
		predictButton.classList.add("is-loading");
		predictButton.innerHTML = '<span class="button-spinner" aria-hidden="true"></span>Loading prediction...';
	}
	resultElement.classList.remove("success");
	resultElement.classList.add("loading");
	resultElement.innerHTML = "<h1>Loading prediction...</h1>";

	try {
		const response = await fetch(`${API_BASE_URL}/predict`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json"
			},
			body: JSON.stringify(data)
		});

		console.log("FETCH URL", `${API_BASE_URL}/predict`);
		console.log("API STATUS:", response.status);
		const result = await response.json();
		console.log("PREDICT RESULT", result);
		console.log(response);

		if (!response.ok) {
			throw new Error(result.error || "Prediction request failed");
		}

		const value = Number(result.predicted_revenue);
		if (!Number.isFinite(value)) {
			throw new Error("The API returned an invalid prediction");
		}

		const duration = Math.round(performance.now() - startedAt);
		resultElement.classList.remove("loading");
		resultElement.classList.add("success");
		resultElement.innerHTML = '<h3>Predicted Revenue</h3><h1 id="animated-prediction">$0.00</h1><p>AI Predicted Revenue</p>';
		animatePredictionValue(document.getElementById("animated-prediction"), value);
		document.getElementById("prediction-time").textContent = `${duration} ms`;
		document.getElementById("last-prediction").textContent = `Last prediction: ${new Date().toLocaleString()}`;
		localStorage.setItem("lastPrediction", resultElement.innerHTML);
		loadPredictionHistory();
	} catch (error) {
		console.error("Prediction error:", error);
		resultElement.classList.remove("loading");
		resultElement.innerHTML = `<h2>${error.message}</h2>`;
	} finally {
		if (predictButton) {
			predictButton.disabled = false;
			predictButton.classList.remove("is-loading");
			predictButton.textContent = "Predict Revenue";
		}
	}
}

function animatePredictionValue(element, target) {
	if (!element) return;
	const start = performance.now();
	const duration = 650;
	function frame(now) {
		const progress = Math.min((now - start) / duration, 1);
		const eased = 1 - Math.pow(1 - progress, 3);
		element.textContent = `$${(target * eased).toFixed(2)}`;
		if (progress < 1) requestAnimationFrame(frame);
	}
	requestAnimationFrame(frame);
}

function restorePredictionInputs() {
	const saved = localStorage.getItem("predictionInputsLegacy");
	if (!saved) return;
	try {
		const values = JSON.parse(saved);
		["OrderCount", "QuantitySold", "Revenue_Lag1", "Revenue_Lag2", "Revenue_Lag3", "Quantity_Lag1"].forEach((id) => {
			if (values[id] !== undefined) document.getElementById(id).value = values[id];
		});
	} catch (error) { console.error("Unable to restore prediction inputs:", error); }
}

function savePredictionInputs() {
	const ids = ["OrderCount", "QuantitySold", "Revenue_Lag1", "Revenue_Lag2", "Revenue_Lag3", "Quantity_Lag1"];
	localStorage.setItem("predictionInputsLegacy", JSON.stringify(Object.fromEntries(ids.map((id) => [id, document.getElementById(id).value]))));
}

async function loadModelPerformance() {
	const statusElement = document.getElementById("performance-status");

	try {
		const response = await fetch(`${API_BASE_URL}/model-performance`, { credentials: "include" });
		const result = await response.json();

		if (!response.ok) {
			throw new Error(result.error || "Model performance request failed");
		}

		document.getElementById("performance-r2").textContent = `${(result.r2 * 100).toFixed(2)}%`;
		document.getElementById("performance-mae").textContent = Number(result.mae).toFixed(2);
		document.getElementById("performance-rmse").textContent = Number(result.rmse).toFixed(2);
		document.getElementById("performance-samples").textContent = result.samples;
		statusElement.textContent = "";
	} catch (error) {
		console.error("Model performance error:", error);
		statusElement.textContent = "Unable to load model performance.";
	}
}

async function loadPredictionHistory() {
	const historyBody = document.getElementById("history-body");
	if (!historyBody) return;

	try {
		const response = await fetch(`${API_BASE_URL}/prediction-history`, { credentials: "include" });
		const history = await response.json();

		if (!response.ok) {
			throw new Error("Prediction history request failed");
		}

		predictionHistory = history;
		predictionHistoryPage = 1;
		updateHistoryKpis(history);
		updatePredictionChart(history);
		renderPredictionHistoryPage();
	} catch (error) {
		console.error("Prediction history error:", error);
		historyBody.innerHTML = "<tr><td colspan=\"4\">Unable to load prediction history</td></tr>";
	}
}

const HISTORY_PAGE_SIZE = 10;
let predictionHistory = [];
let predictionHistoryPage = 1;

function renderPredictionHistoryPage() {
	const historyBody = document.getElementById("history-body");
	const pagination = document.getElementById("history-pagination");
	if (!historyBody) return;

	if (predictionHistory.length === 0) {
		historyBody.innerHTML = "<tr><td colspan=\"4\">No prediction history</td></tr>";
		if (pagination) pagination.hidden = true;
		return;
	}

	const totalPages = Math.ceil(predictionHistory.length / HISTORY_PAGE_SIZE);
	predictionHistoryPage = Math.min(predictionHistoryPage, totalPages);
	const start = (predictionHistoryPage - 1) * HISTORY_PAGE_SIZE;
	const pageRecords = predictionHistory.slice(start, start + HISTORY_PAGE_SIZE);
	historyBody.innerHTML = pageRecords.map((record) => `
		<tr>
			<td>${record.created_at}</td>
			<td>${record.order_count}</td>
			<td>${Number(record.actual_revenue).toFixed(2)}</td>
			<td>${Number(record.predicted_revenue).toFixed(2)}</td>
		</tr>
	`).join("");

	if (!pagination) return;
	pagination.hidden = totalPages <= 1;
	pagination.querySelector("[data-history-page]").textContent = `Page ${predictionHistoryPage} of ${totalPages}`;
	pagination.querySelector("[data-history-previous]").disabled = predictionHistoryPage === 1;
	pagination.querySelector("[data-history-next]").disabled = predictionHistoryPage === totalPages;
}

function changePredictionHistoryPage(offset) {
	predictionHistoryPage += offset;
	renderPredictionHistoryPage();
}

async function clearPredictionHistory() {
	if (!window.confirm("Clear all prediction history?")) return;

	try {
		const response = await fetch(`${API_BASE_URL}/history`, {
			method: "DELETE",
			credentials: "include"
		});
		const result = await response.json();
		if (!response.ok) throw new Error(result.error || "Unable to clear prediction history.");
		await loadPredictionHistory();
	} catch (error) {
		console.error("Clear prediction history error:", error);
	}
}

async function loadModelTrainingData() {
	try {
		const [infoResponse, historyResponse] = await Promise.all([
			fetch(`${API_BASE_URL}/model-info`, { credentials: "include" }),
			fetch(`${API_BASE_URL}/model-training-history`, { credentials: "include" })
		]);
		const info = await infoResponse.json();
		const history = await historyResponse.json();

		if (!infoResponse.ok || !historyResponse.ok) {
			throw new Error("Model training data request failed");
		}

		document.getElementById("current-model").textContent = info.model || "--";
		document.getElementById("current-model-accuracy").textContent = info.r2
			? `${(Number(info.r2) * 100).toFixed(2)}%`
			: "--";

		const historyBody = document.getElementById("model-history-body");
		if (history.length === 0) {
			historyBody.innerHTML = "<tr><td colspan=\"5\">No model training history</td></tr>";
		} else {
			historyBody.innerHTML = history.map((record) => `
				<tr>
					<td>${record.created_at}</td>
					<td>${record.model_name}</td>
					<td>${Number(record.r2_score).toFixed(4)}</td>
					<td>${Number(record.mae).toFixed(2)}</td>
					<td>${Number(record.rmse).toFixed(2)}</td>
				</tr>
			`).join("");
		}
	} catch (error) {
		console.error("Model training data error:", error);
		document.getElementById("training-status").textContent = "Unable to load model training data.";
	}
}

async function trainNewModel() {
	const fileInput = document.getElementById("training-file");
	const statusElement = document.getElementById("training-status");
	const file = fileInput.files[0];

	if (!file) {
		statusElement.textContent = "Select a CSV file first.";
		return;
	}

	const formData = new FormData();
	formData.append("file", file);
	statusElement.textContent = "Training model...";

	try {
		const response = await fetch(`${API_BASE_URL}/train`, {
			method: "POST",
			credentials: "include",
			body: formData
		});
		const result = await response.json();

		if (!response.ok || result.status !== "success") {
			throw new Error(result.message || "Model training failed");
		}

		statusElement.textContent = `${result.message} Accuracy: ${(Number(result.r2) * 100).toFixed(2)}%`;
		await loadModelTrainingData();
		await loadModelPerformance();
	} catch (error) {
		console.error("Model training error:", error);
		statusElement.textContent = error.message;
	}
}

function updateHistoryKpis(history) {
	const predictions = history.map((record) => Number(record.predicted_revenue));
	const total = predictions.length;

	document.getElementById("total-predictions").textContent = total;
	document.getElementById("average-prediction").textContent = total
		? (predictions.reduce((sum, value) => sum + value, 0) / total).toFixed(2)
		: "--";
	document.getElementById("highest-forecast").textContent = total
		? Math.max(...predictions).toFixed(2)
		: "--";
	document.getElementById("latest-forecast").textContent = total
		? predictions[0].toFixed(2)
		: "--";
}

function updatePredictionChart(history) {
	const chartElement = document.getElementById("prediction-chart");
	if (!chartElement || typeof Chart === "undefined") {
		return;
	}

	if (window.predictionChart) {
		window.predictionChart.destroy();
	}

	const chartHistory = [...history].reverse();
	window.predictionChart = new Chart(chartElement, {
		type: "line",
		data: {
			labels: chartHistory.map((record) => record.created_at),
			datasets: [
			{
				label: "Actual Revenue",
				data: chartHistory.map((record) => Number(record.actual_revenue)),
				borderColor: "#16a34a",
				backgroundColor: "rgba(22, 163, 74, 0.10)",
				fill: false,
				tension: 0.25
			},
			{
				label: "AI Predicted Revenue",
				data: chartHistory.map((record) => Number(record.predicted_revenue)),
				borderColor: "#2563eb",
				backgroundColor: "rgba(37, 99, 235, 0.12)",
				fill: false,
				tension: 0.25
			}
		]
		},
		options: {
			responsive: true,
			maintainAspectRatio: false,
			plugins: {
				title: {
					display: true,
					text: "Actual Revenue vs AI Forecast"
				}
			},
			scales: {
				x: {
					title: {
						display: true,
						text: "Date"
					}
				},
				y: {
					title: {
						display: true,
						text: "Revenue"
					}
				}
			}
		}
	});
}

function exportPredictionHistory() {
	fetch(`${API_BASE_URL}/prediction-history`, { credentials: "include" })
		.then((response) => response.json().then((data) => ({ response, data })))
		.then(({ response, data }) => {
			if (!response.ok) {
				throw new Error("Prediction history export failed");
			}

			const header = ["Date", "Order Count", "Actual Revenue", "AI Prediction"];
			const rows = data.map((record) => [
				record.created_at,
				record.order_count,
				record.actual_revenue,
				record.predicted_revenue
			]);
			const csv = [header, ...rows]
				.map((row) => row.map((value) => `"${String(value ?? "").replaceAll("\"", "\"\"")}"`).join(","))
				.join("\n");
			const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
			const link = document.createElement("a");
			link.href = URL.createObjectURL(blob);
			link.download = "prediction_history.csv";
			link.click();
			URL.revokeObjectURL(link.href);
		})
		.catch((error) => console.error("Prediction history export error:", error));
}

async function loadCurrentUser() {
	const response = await fetch(`${API_BASE_URL}/current-user`, { credentials: "include" });
	const result = await response.json();
	if (!result.user) {
		window.location.href = "login.html";
		return null;
	}

	const userName = document.getElementById("user-name");
	const userRole = document.getElementById("user-role");
	if (!userName || !userRole) return result.user;
	userName.textContent = result.user.username;
	userRole.textContent = result.user.role;
	if (result.user.role !== "Admin") {
		const trainingSection = document.getElementById("training-section");
		if (trainingSection) trainingSection.hidden = true;
	}
	if (result.user.role === "Viewer") {
		const forecastSection = document.getElementById("forecast-section");
		if (forecastSection) forecastSection.hidden = true;
	}
	const clearHistoryButton = document.getElementById("clear-history");
	if (clearHistoryButton && result.user.role !== "Admin") clearHistoryButton.hidden = true;
	return result.user;
}

async function logout() {
	await fetch(`${API_BASE_URL}/logout`, {
		method: "POST",
		credentials: "include"
	});
	window.location.href = "login.html";
}

async function loadAnalytics() {
	if (!document.getElementById("analytics-total")) return;
	try {
		const [analyticsResponse, trendsResponse, performanceResponse] = await Promise.all([
			fetch(`${API_BASE_URL}/analytics`, { credentials: "include" }),
			fetch(`${API_BASE_URL}/sales-trends`, { credentials: "include" }),
			fetch(`${API_BASE_URL}/model-performance`, { credentials: "include" })
		]);
		const analytics = await analyticsResponse.json();
		const trends = await trendsResponse.json();
		const performance = await performanceResponse.json();

		document.getElementById("analytics-total").textContent = Number(analytics.total_revenue).toFixed(2);
		document.getElementById("analytics-average").textContent = Number(analytics.average_revenue).toFixed(2);
		document.getElementById("analytics-growth").textContent = `${Number(analytics.growth_rate).toFixed(2)}%`;
		document.getElementById("analytics-accuracy").textContent = `${(Number(performance.r2) * 100).toFixed(2)}%`;
		document.getElementById("analytics-best-day").textContent = analytics.best_sales_day || "--";
		document.getElementById("analytics-highest").textContent = Number(analytics.highest_revenue).toFixed(2);

		["daily", "weekly", "monthly"].forEach((period) => {
			const canvas = document.getElementById(`${period}-chart`);
			if (!canvas || typeof Chart === "undefined") return;
			new Chart(canvas, {
				type: "line",
				data: {
					labels: trends[period].map((item) => item.label),
					datasets: [{
						label: `${period[0].toUpperCase()}${period.slice(1)} Revenue`,
						data: trends[period].map((item) => Number(item.revenue)),
						borderColor: "#2563eb",
						backgroundColor: "rgba(37, 99, 235, 0.12)",
						fill: true,
						tension: 0.25
					}]
				},
				options: { responsive: true, maintainAspectRatio: false }
			});
		});
	} catch (error) {
		console.error("Analytics error:", error);
	}
}

document.addEventListener("DOMContentLoaded", async () => {
	restorePredictionInputs();
	["OrderCount", "QuantitySold", "Revenue_Lag1", "Revenue_Lag2", "Revenue_Lag3", "Quantity_Lag1"].forEach((id) => {
		const input = document.getElementById(id);
		if (input) {
			input.addEventListener("input", savePredictionInputs);
			input.addEventListener("change", savePredictionInputs);
		}
	});
	const user = await loadCurrentUser();
	if (!user) return;
	const savedPrediction = localStorage.getItem("lastPrediction");
	if (savedPrediction && document.getElementById("result")) {
		document.getElementById("result").innerHTML = savedPrediction;
	}

	loadModelPerformance();
	if (document.getElementById("model-history-body")) loadModelTrainingData();
	loadPredictionHistory();
	const exportButton = document.getElementById("export-history");
	if (exportButton) exportButton.addEventListener("click", exportPredictionHistory);
	const clearHistoryButton = document.getElementById("clear-history");
	if (clearHistoryButton) clearHistoryButton.addEventListener("click", clearPredictionHistory);
	const previousHistoryButton = document.querySelector("[data-history-previous]");
	if (previousHistoryButton) previousHistoryButton.addEventListener("click", () => changePredictionHistoryPage(-1));
	const nextHistoryButton = document.querySelector("[data-history-next]");
	if (nextHistoryButton) nextHistoryButton.addEventListener("click", () => changePredictionHistoryPage(1));
	const trainButton = document.getElementById("train-model");
	if (trainButton) trainButton.addEventListener("click", trainNewModel);
	const logoutButton = document.getElementById("logout-button");
	if (logoutButton) logoutButton.addEventListener("click", logout);
	loadAnalytics();
});