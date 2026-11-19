/*
  main.js - Small helpers used on every page.

  1. Turns <i data-lucide="..."> placeholders into real icons
  2. Opens and closes the mobile navigation menu
  3. Lets people close the coloured flash notices
*/

// ---------- 1. Icons ----------

function drawIcons() {
    // "lucide" is loaded from the CDN script tag in base.html
    if (window.lucide) {
        window.lucide.createIcons({ attrs: { "stroke-width": 1.75 } });
    }
}


// ---------- 2. Mobile navigation menu ----------

function setupMobileMenu() {
    const toggleButton = document.getElementById("nav-toggle");
    const menu = document.getElementById("nav-menu");

    // Pages without the public navbar (like the student app) skip this
    if (!toggleButton || !menu) {
        return;
    }

    toggleButton.addEventListener("click", function () {
        const isOpen = menu.classList.toggle("is-open");
        toggleButton.setAttribute("aria-expanded", String(isOpen));
    });

    // The Escape key closes the menu and returns focus to the button
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && menu.classList.contains("is-open")) {
            menu.classList.remove("is-open");
            toggleButton.setAttribute("aria-expanded", "false");
            toggleButton.focus();
        }
    });
}


// ---------- 3. Flash notices ----------

function setupFlashClose() {
    const closeButtons = document.querySelectorAll(".flash__close");

    closeButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            button.closest(".flash").remove();
        });
    });
}


// Start everything once the page has loaded
document.addEventListener("DOMContentLoaded", function () {
    drawIcons();
    setupMobileMenu();
    setupFlashClose();
});
