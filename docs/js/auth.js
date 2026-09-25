const AUTH_API = window.API_BASE_URL || "https://ai-sales-intelligence-saas.onrender.com";
async function logoutUser() {
    const logoutUrl = `${AUTH_API}/logout`;
    console.log("FETCH URL", logoutUrl);
    await fetch(logoutUrl, { method: "POST", credentials: "include" });
    window.location.href = "login.html";
}
document.addEventListener("DOMContentLoaded", () => document.getElementById("logout-button")?.addEventListener("click", logoutUser));
