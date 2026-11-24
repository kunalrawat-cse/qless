/*
  order.js - The live order page.

  What happens here:
    1. Ask the server for the order (GET /api/orders/<id>)
    2. Draw the 4-step tracker, the QR + 4-digit OTP card and the order summary
    3. Ask again every few seconds (the polling speed comes from config.py)
       until the order is collected or cancelled
    4. Save the pickup code in this browser (localStorage). If the server cannot
       be reached later, the saved code is shown instead, so the student can
       still collect the food.
    5. Let the student cancel while it is still allowed

  The QR code contains the order's secret token. The 4-digit OTP is the backup
  that staff can type in. Phase 6 uses both at the counter.
*/

const orderPage = document.getElementById("order-page");
const orderId = Number(orderPage.dataset.orderId);
const pollSeconds = Number(getAppElement().dataset.pollSeconds) || 15;
const pickupCacheKey = "qless_pickup_" + getUserId() + "_" + orderId;

let previousStatus = null;        // Used to detect "just became ready"
let hasLoadedOnce = false;
let pollTimer = null;
let drawnQrToken = null;          // So we only draw the QR once per code

const loadingBox = document.getElementById("order-loading");
const contentBox = document.getElementById("order-content");
const bannerBox = document.getElementById("order-banner");
const summarySection = document.querySelector('[aria-labelledby="summary-title"]');
const cancelButton = document.getElementById("cancel-button");
const cancelHint = document.getElementById("cancel-hint");

// Words shown for each status (edit the wording here)
const statusTitles = {
    confirmed: "Order confirmed",
    preparing: "Preparing your order",
    ready: "Ready for pickup!",
    collected: "Collected. Enjoy your meal!",
    cancelled: "Order cancelled",
};


// =========================================================
// Loading and polling
// =========================================================

async function loadOrder() {
    // No point asking the server while the tab is in the background
    if (document.hidden && hasLoadedOnce) {
        scheduleNextPoll();
        return;
    }

    try {
        const order = await apiGet("/api/orders/" + orderId);

        hideBanner();
        notifyIfStatusChanged(order);
        renderOrder(order);
        savePickupCache(order);
        hasLoadedOnce = true;

        // Stop polling once nothing more can change
        if (order.status !== "collected" && order.status !== "cancelled") {
            scheduleNextPoll();
        }
    } catch (error) {
        handleLoadFailure(error);
    }
}

function scheduleNextPoll() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(loadOrder, pollSeconds * 1000);
}

function handleLoadFailure(error) {
    loadingBox.hidden = true;

    // The order does not exist (or is not yours): do not keep retrying
    if (error.status === 404) {
        showBanner(error.message);
        return;
    }

    const cached = readPickupCache();

    if (hasLoadedOnce) {
        showBanner("Connection lost. Showing the last update. We will keep trying.");
    } else if (cached) {
        renderFromCache(cached);
        showBanner("You seem to be offline. Showing your saved pickup code. The status will update when you reconnect.");
    } else {
        showBanner(error.message);
    }

    scheduleNextPoll();
}

function showBanner(message) {
    document.getElementById("order-banner-text").textContent = message;
    bannerBox.hidden = false;
    drawIcons();
}

function hideBanner() {
    bannerBox.hidden = true;
}


// =========================================================
// Notifications for status changes
// =========================================================

function notifyIfStatusChanged(order) {
    // Only after the first load, so opening the page does not pop a toast
    if (previousStatus !== null && previousStatus !== order.status) {
        if (order.status === "preparing") {
            showToast("The kitchen has started preparing your order.", "info");
        } else if (order.status === "ready") {
            showToast("Your order is ready for pickup!", "success");
        }
    }
    previousStatus = order.status;
}


// =========================================================
// Drawing the page
// =========================================================

function renderOrder(order) {
    loadingBox.hidden = true;
    contentBox.hidden = false;
    summarySection.hidden = false;

    renderHeading(order);
    renderTracker(order);
    renderPickupCard(order);
    renderSummary(order);
    renderCancelArea(order);
    drawIcons();
}

function renderHeading(order) {
    document.getElementById("order-title").textContent = statusTitles[order.status];

    let subtitle = "Order #" + order.id + " · Pickup " + order.slot_when.toLowerCase() + " (" + order.slot_label + ")";

    // A countdown is only useful before the food is ready
    if ((order.status === "confirmed" || order.status === "preparing") && order.minutes_to_pickup > 0) {
        subtitle += " · in " + order.minutes_to_pickup + " min";
    }

    document.getElementById("order-subtitle").textContent = subtitle;

    // Subtle green pulse once the food is ready (CSS does the animation)
    contentBox.classList.toggle("is-ready", order.status === "ready");
}

function renderTracker(order) {
    const isCancelled = order.status === "cancelled";

    document.getElementById("tracker-section").hidden = isCancelled;
    document.getElementById("cancelled-box").hidden = !isCancelled;

    if (isCancelled) {
        return;
    }

    document.querySelectorAll("#tracker .tracker__step").forEach(function (stepElement) {
        const stepNumber = Number(stepElement.dataset.step);
        const isCurrent = stepNumber === order.step;

        stepElement.classList.toggle("is-done", stepNumber < order.step || order.status === "collected");
        stepElement.classList.toggle("is-current", isCurrent);

        if (isCurrent) {
            stepElement.setAttribute("aria-current", "step");
        } else {
            stepElement.removeAttribute("aria-current");
        }
    });

    // The green bar fills from 0% (step 1) to 100% (step 4)
    document.getElementById("tracker-fill").style.width = ((order.step - 1) / 3 * 100) + "%";
}

function renderPickupCard(order) {
    const card = document.getElementById("pickup-card");
    const isCancelled = order.status === "cancelled";
    const isUsed = order.status === "collected";

    card.hidden = isCancelled;
    card.classList.toggle("is-used", isUsed);

    if (isCancelled) {
        return;
    }

    drawPickupCode(order.qr_token, order.pickup_otp);

    let note = "Keep this screen ready when you arrive.";
    if (order.status === "ready") {
        note = "Your order is ready. Show this code at the counter now.";
    } else if (isUsed) {
        note = "This code has been used.";
    }
    if (order.is_uncollected && order.status === "ready") {
        note = "Your order is waiting at the counter. Please collect it soon.";
    }
    document.getElementById("pickup-note").textContent = note;
}

function drawPickupCode(qrToken, otp) {
    document.getElementById("otp-text").textContent = otp;

    const qrBox = document.getElementById("qr-box");

    // Draw the QR only once per code, so the 15-second refresh does not flicker
    if (drawnQrToken === qrToken) {
        return;
    }
    drawnQrToken = qrToken;
    qrBox.innerHTML = "";

    // "QRCode" comes from the library loaded in order.html. If it failed to load, the OTP still works.
    if (typeof QRCode === "undefined") {
        qrBox.innerHTML = '<p class="text-small text-soft">QR code unavailable. Use the 4-digit code below.</p>';
        return;
    }

    new QRCode(qrBox, {
        text: qrToken,
        width: 176,
        height: 176,
        colorDark: "#064E3B",
        colorLight: "#FFFFFF",
        correctLevel: QRCode.CorrectLevel.M,
    });
}

function describePayment(order) {
    if (order.payment_status === "refunded") {
        return "Refunded (demo payment).";
    }
    if (order.payment_method === "mock_upi") {
        return "Paid with UPI (demo payment).";
    }
    if (order.payment_status === "paid") {
        return "Paid at the counter.";
    }
    return "Pay " + formatPrice(order.total_amount) + " at the counter when you collect.";
}

function renderSummary(order) {
    document.getElementById("summary-list").innerHTML = order.items.map(function (item) {
        return `
          <li class="summary-list__row">
            <span class="summary-list__dish">
              ${item.image_url ? `<img class="summary-list__thumb" src="${escapeHtml(item.image_url)}" alt="" width="44" height="44" loading="lazy" onerror="this.remove()">` : ""}
              <span>${foodDotHtml(item.food_type)} <span class="num">${item.quantity} ×</span> ${escapeHtml(item.name)}</span>
            </span>
            <span class="num">${formatPrice(item.unit_price * item.quantity)}</span>
          </li>`;
    }).join("");

    document.getElementById("summary-total").textContent = formatPrice(order.total_amount);
    document.getElementById("payment-note").textContent = describePayment(order);
}

function renderCancelArea(order) {
    cancelButton.hidden = !order.can_cancel;
    cancelHint.hidden = true;

    if (order.can_cancel) {
        return;
    }

    // Explain why the button is missing (only while the order is still in progress)
    if (order.status === "confirmed") {
        cancelHint.textContent = "It is too close to the pickup time to cancel this order.";
        cancelHint.hidden = false;
    } else if (order.status === "preparing") {
        cancelHint.textContent = "The kitchen has started preparing, so this order can no longer be cancelled.";
        cancelHint.hidden = false;
    }
}


// =========================================================
// Saved pickup code (works even when the connection drops)
// =========================================================

function savePickupCache(order) {
    try {
        // Finished orders do not need a saved code any more
        if (order.status === "collected" || order.status === "cancelled") {
            localStorage.removeItem(pickupCacheKey);
            return;
        }

        localStorage.setItem(pickupCacheKey, JSON.stringify({
            otp: order.pickup_otp,
            qrToken: order.qr_token,
            slotWhen: order.slot_when,
            slotLabel: order.slot_label,
            savedAt: Date.now(),
        }));
    } catch (error) {
        // Storage blocked or full: the page still works online
    }
}

function readPickupCache() {
    try {
        return JSON.parse(localStorage.getItem(pickupCacheKey));
    } catch (error) {
        return null;
    }
}

function renderFromCache(cached) {
    loadingBox.hidden = true;
    contentBox.hidden = false;

    // Only the pickup card is shown: we cannot know the live status offline
    document.getElementById("tracker-section").hidden = true;
    document.getElementById("cancelled-box").hidden = true;
    summarySection.hidden = true;

    document.getElementById("order-title").textContent = "Saved pickup code";
    document.getElementById("order-subtitle").textContent =
        "Order #" + orderId + " · Pickup " + cached.slotWhen.toLowerCase() + " (" + cached.slotLabel + ")";

    document.getElementById("pickup-card").hidden = false;
    drawPickupCode(cached.qrToken, cached.otp);
    document.getElementById("pickup-note").textContent = "Saved on this phone when you placed the order.";
    drawIcons();
}


// =========================================================
// Cancelling
// =========================================================

cancelButton.addEventListener("click", async function () {
    if (!window.confirm("Cancel this order? Your dishes go back on the menu.")) {
        return;
    }

    cancelButton.disabled = true;

    try {
        const order = await apiPost("/api/orders/" + orderId + "/cancel");
        renderOrder(order);
        savePickupCache(order);
        previousStatus = order.status;
        showToast("Your order was cancelled.", "info");
    } catch (error) {
        showToast(error.message, "error");
        loadOrder();           // Refresh, in case the kitchen just started preparing
    } finally {
        cancelButton.disabled = false;
    }
});


// =========================================================
// Start
// =========================================================

document.getElementById("order-retry").addEventListener("click", loadOrder);

// Coming back to the tab refreshes straight away
document.addEventListener("visibilitychange", function () {
    if (!document.hidden && hasLoadedOnce) {
        loadOrder();
    }
});

loadOrder();
