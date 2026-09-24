(() => {
    const page = location.pathname.split("/").pop() || "dashboard.html";
    const aliases = { model: "training.html", business: "powerbi.html" };
    document.querySelectorAll("[data-nav-page]").forEach((link) => {
        const target = link.dataset.navPage;
        const canonical = aliases[target.replace(".html", "")] || target;
        link.classList.toggle("active", canonical === page);
    });
    document.querySelectorAll("[data-menu-toggle]").forEach((button) => button.addEventListener("click", () => document.querySelector(".sidebar")?.classList.toggle("open")));
})();
