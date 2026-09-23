(() => {
    const savedTheme = localStorage.getItem("ai-sales-theme") || "light";
    document.documentElement.dataset.theme = savedTheme;

    window.setTheme = (theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem("ai-sales-theme", theme);
        document.querySelectorAll("[data-theme-toggle]").forEach((toggle) => {
            toggle.checked = theme === "dark";
        });
    };

    window.toggleTheme = (event) => {
        window.setTheme(event.target.checked ? "dark" : "light");
    };

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("[data-theme-toggle]").forEach((toggle) => {
            toggle.checked = savedTheme === "dark";
            toggle.addEventListener("change", window.toggleTheme);
        });
        document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
            button.addEventListener("click", () => document.querySelector(".sidebar")?.classList.toggle("open"));
        });
    });
})();
