/*
  common.js - Small helpers shared by every student page.

  Loaded first, so cart.js, menu.js and order.js can use these functions:
    escapeHtml(text)        make text safe to put inside HTML
    formatPrice(number)     12 -> "₹12", 12.5 -> "₹12.50"
    apiGet(url)             fetch JSON from the server
    apiPost(url, body)      send JSON to the server (adds the CSRF token for us)
    showToast(message)      small message that fades away on its own
    openPanel / closePanel  show and hide the drawer and the modal (with keyboard support)
*/

// ---------- Reading values the page gave us ----------

function getAppElement() {
    return document.getElementById("student-app");
}

function getUserId() {
    return getAppElement().dataset.userId;
}


// ---------- Text helpers ----------

function escapeHtml(text) {
    // Never put database text into innerHTML without this
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function formatPrice(amount) {
    const number = Number(amount);
    return "₹" + (Number.isInteger(number) ? number : number.toFixed(2));
}

function foodDotHtml(foodType) {
    // food_type from the database: "veg", "non_veg" or "egg"
    const extraClass = foodType === "non_veg" ? " food-dot--non-veg" : foodType === "egg" ? " food-dot--egg" : "";
    const label = foodType === "non_veg" ? "Non-vegetarian" : foodType === "egg" ? "Contains egg" : "Vegetarian";
    return `<span class="food-dot${extraClass}" role="img" aria-label="${label}"></span>`;
}


// ---------- Talking to the server ----------

class ApiError extends Error {
    // Carries the server's message plus extra details (like a suggested slot)
    constructor(message, status, data) {
        super(message);
        this.status = status;
        this.data = data || {};
    }
}

async function apiRequest(url, options) {
    let response;

    try {
        response = await fetch(url, options);
    } catch (networkError) {
        // No internet, or the server is switched off
        throw new ApiError("Cannot reach Qless. Check your connection and try again.", 0);
    }

    // The server might send an HTML error page instead of JSON, so read carefully
    let data = {};
    try {
        data = await response.json();
    } catch (parseError) {
        data = {};
    }

    if (!response.ok) {
        if (response.status === 401) {
            // Session ended: go to the login page and come back afterwards
            window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
        }
        throw new ApiError(data.error || "Something went wrong. Please try again.", response.status, data);
    }

    return data;
}

function apiGet(url) {
    return apiRequest(url, { headers: { Accept: "application/json" } });
}

function apiPost(url, body) {
    const token = document.querySelector('meta[name="csrf-token"]').content;

    return apiRequest(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-CSRF-Token": token,
        },
        body: JSON.stringify(body || {}),
    });
}


// ---------- Toasts ----------

function showToast(message, kind) {
    const area = document.getElementById("toast-area");
    const toast = document.createElement("div");
    toast.className = "toast toast--" + (kind || "info");
    toast.textContent = message;
    area.appendChild(toast);

    // Remove it after 3.5 seconds
    setTimeout(function () {
        toast.classList.add("is-leaving");
        setTimeout(function () { toast.remove(); }, 250);
    }, 3500);
}


// ---------- Drawer and modal behaviour ----------
// Both are "panels": a box plus a dark backdrop. These two functions handle
// opening, closing, the Escape key, and keeping Tab inside the open panel.

let currentPanel = null;

function openPanel(panel, backdrop) {
    currentPanel = { panel: panel, backdrop: backdrop, previousFocus: document.activeElement };

    backdrop.hidden = false;
    panel.setAttribute("aria-hidden", "false");

    // Wait one frame so the slide-in animation runs
    requestAnimationFrame(function () {
        backdrop.classList.add("is-open");
        panel.classList.add("is-open");
    });

    document.body.classList.add("no-scroll");

    const firstFocusable = panel.querySelector("button, a, input, select");
    if (firstFocusable) {
        firstFocusable.focus();
    }
}

function closePanel() {
    if (!currentPanel) {
        return;
    }

    const { panel, backdrop, previousFocus } = currentPanel;
    currentPanel = null;

    panel.classList.remove("is-open");
    backdrop.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
    document.body.classList.remove("no-scroll");

    // Hide the backdrop after the fade-out finishes
    setTimeout(function () { backdrop.hidden = true; }, 250);

    if (previousFocus && previousFocus.focus) {
        previousFocus.focus();
    }
}

document.addEventListener("keydown", function (event) {
    if (!currentPanel) {
        return;
    }

    if (event.key === "Escape") {
        closePanel();
        return;
    }

    // Keep keyboard focus inside the open panel
    if (event.key === "Tab") {
        const focusable = currentPanel.panel.querySelectorAll(
            "button:not([disabled]), a[href], input:not([disabled]), select, [tabindex='0']"
        );
        if (focusable.length === 0) {
            return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }
});
