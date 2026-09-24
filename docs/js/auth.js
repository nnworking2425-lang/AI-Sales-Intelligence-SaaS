const API_BASE_URL = "";
const AUTH_API = API_BASE_URL;
async function logoutUser() { await fetch(`${AUTH_API}/logout`, { method: "POST", credentials: "include" }); window.location.href = "login.html"; }
document.addEventListener("DOMContentLoaded", () => document.getElementById("logout-button")?.addEventListener("click", logoutUser));
