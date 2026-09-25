const defaultApiBaseUrl = "https://ai-sales-intelligence-saas.onrender.com";
const localHostnames = new Set(["localhost", "127.0.0.1"]);
const isLocalEnvironment = window.location.protocol === "file:" || !window.location.hostname || localHostnames.has(window.location.hostname);
window.API_BASE_URL = isLocalEnvironment ? "http://127.0.0.1:5000" : defaultApiBaseUrl;
const API_BASE_URL = window.API_BASE_URL;
