const AUTH_API = "http://127.0.0.1:5000";
async function logoutUser() { await fetch(`${AUTH_API}/logout`, { method: "POST", credentials: "include" }); window.location.href = "login.html"; }
document.addEventListener("DOMContentLoaded", () => document.getElementById("logout-button")?.addEventListener("click", logoutUser));
