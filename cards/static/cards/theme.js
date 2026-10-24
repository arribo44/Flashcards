// cards/static/cards/theme.js

// Apply the light/dark theme before the page is drawn, to avoid a flash.
// Same logic as AdminLTE's starter page (MIT); its bundle then handles the
// theme menu (buttons with data-bs-theme-value) and saves the choice.
(() => {
    const root = document.documentElement;
    let stored = null;
    try {
        stored = localStorage.getItem("lte-theme");
    } catch {
        // Storage may be unavailable (private browsing)
    }
    let resolved = "light";
    if (stored === "dark" || stored === "light") {
        resolved = stored;
    } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        resolved = "dark";
    }
    root.setAttribute("data-bs-theme", resolved);
    root.style.colorScheme = resolved;
    root.setAttribute("data-lte-theme-resolved", "");
})();
