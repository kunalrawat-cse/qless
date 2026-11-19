/*
  cart.js - The cart drawer: cart lines, pickup slot picker, payment and checkout.

  The cart is saved in the browser (localStorage), one cart per student, so it
  survives page refreshes. The server never trusts it: when you press
  "Place order" the server re-checks prices, stock and the slot.

  Other files use the small public object at the bottom:
      Cart.addItem(item)   Cart.open()   Cart.setMaxQty(number)
*/

const cartStorageKey = "qless_cart_" + getUserId();
const simulatedPaymentDelayMs = 900;      // How long the fake "Processing payment" step lasts

// ---------- Cart state ----------

let cartLines = [];             // [{ itemId, name, price, foodType, quantity, stock }]
let maxQtyPerItem = 10;         // Replaced by the server's value when the menu loads

// ---------- Drawer state ----------

let drawerStatus = "idle";      // "idle" | "loading" | "ready" | "error"
let drawerErrorText = "";
let slotData = null;            // Answer from /api/slots
let slotMode = "next";          // "next" = Next Available Slot, "later" = pick any open slot
let selectedSlotId = null;
let paymentMethod = "mock_upi"; // "mock_upi" (simulated) or "counter"
let checkoutError = "";
let isPlacingOrder = false;

const drawerElement = document.getElementById("cart-drawer");
const drawerBackdrop = document.getElementById("cart-backdrop");
const cartBodyElement = document.getElementById("cart-body");
const cartFooterElement = document.getElementById("cart-footer");


// =========================================================
// Saving and loading the cart
// =========================================================

function loadCart() {
    try {
        const saved = JSON.parse(localStorage.getItem(cartStorageKey));
        if (Array.isArray(saved)) {
            cartLines = saved.filter(function (line) {
                return line && Number.isInteger(line.itemId) && Number.isInteger(line.quantity) && line.quantity > 0;
            });
        }
    } catch (error) {
        // Private browsing or damaged data: start with an empty cart
        cartLines = [];
    }
}

function saveCart() {
    try {
        localStorage.setItem(cartStorageKey, JSON.stringify(cartLines));
    } catch (error) {
        // Storage full or blocked. The cart still works until the page closes.
    }
}


// =========================================================
// Cart maths
// =========================================================

function getCartCount() {
    return cartLines.reduce(function (sum, line) { return sum + line.quantity; }, 0);
}

function getCartTotal() {
    const total = cartLines.reduce(function (sum, line) { return sum + line.price * line.quantity; }, 0);
    return Math.round(total * 100) / 100;      // Avoids 0.1 + 0.2 style rounding noise
}

function getLineLimit(line) {
    // You cannot order more than is in stock, or more than the per-dish limit
    return Math.min(line.stock, maxQtyPerItem);
}

function findLine(itemId) {
    return cartLines.find(function (line) { return line.itemId === itemId; });
}


// =========================================================
// Changing the cart
// =========================================================

function addItem(item) {
    // Returns true if the dish was added, so the menu card can show "Added"
    if (!item.available) {
        showToast(item.name + " is sold out.", "error");
        return false;
    }

    const line = findLine(item.id);
    const quantityNow = line ? line.quantity : 0;
    const limit = Math.min(item.stock_qty, maxQtyPerItem);

    if (quantityNow + 1 > limit) {
        showToast(limit === item.stock_qty ? "Only " + item.stock_qty + " left of " + item.name + "." : "You can order up to " + maxQtyPerItem + " of each dish.", "error");
        return false;
    }

    if (line) {
        line.quantity += 1;
        line.stock = item.stock_qty;
    } else {
        cartLines.push({
            itemId: item.id,
            name: item.name,
            price: item.price,
            foodType: item.food_type,
            quantity: 1,
            stock: item.stock_qty,
        });
    }

    saveCart();
    updateCartDisplay(true);
    return true;
}

function changeQuantity(itemId, change) {
    const line = findLine(itemId);
    if (!line) {
        return;
    }

    const newQuantity = line.quantity + change;

    if (newQuantity < 1) {
        removeLine(itemId);
        return;
    }

    if (newQuantity > getLineLimit(line)) {
        showToast("That is the most you can order of " + line.name + ".", "error");
        return;
    }

    line.quantity = newQuantity;
    saveCart();
    updateCartDisplay(false);
    renderDrawer();
}

function removeLine(itemId) {
    cartLines = cartLines.filter(function (line) { return line.itemId !== itemId; });
    saveCart();
    updateCartDisplay(false);
    renderDrawer();
}

function clearCart() {
    cartLines = [];
    saveCart();
    updateCartDisplay(false);
}

function syncCartWithMenu(menuItems) {
    // Make the saved cart match today's real prices and stock
    const notes = [];

    cartLines = cartLines.filter(function (line) {
        const item = menuItems.find(function (menuItem) { return menuItem.id === line.itemId; });

        if (!item || !item.available) {
            notes.push(line.name + " is no longer available and was removed.");
            return false;
        }

        line.name = item.name;
        line.price = item.price;
        line.foodType = item.food_type;
        line.stock = item.stock_qty;

        const limit = getLineLimit(line);
        if (line.quantity > limit) {
            line.quantity = limit;
            notes.push("Only " + limit + " " + line.name + " left, so we lowered the quantity.");
        }

        return true;
    });

    saveCart();
    updateCartDisplay(false);

    if (notes.length > 0) {
        showToast(notes.join(" "), "info");
    }
}


// =========================================================
// The cart badge in the top bar and the "View cart" bar on phones
// =========================================================

function updateCartDisplay(shouldBump) {
    const count = getCartCount();
    const badge = document.getElementById("cart-badge");
    const cartBar = document.getElementById("cart-bar");

    badge.textContent = count;
    badge.hidden = count === 0;

    // Little scale animation when something is added
    if (shouldBump) {
        badge.classList.remove("is-bumped");
        void badge.offsetWidth;          // Restarts the CSS animation
        badge.classList.add("is-bumped");
    }

    // The mobile bar only exists on the menu page
    if (cartBar) {
        cartBar.hidden = count === 0;
        document.getElementById("cart-bar-count").textContent = count + (count === 1 ? " item" : " items");
        document.getElementById("cart-bar-total").textContent = formatPrice(getCartTotal());
    }
}


// =========================================================
// Opening and closing the drawer
// =========================================================

async function openCartDrawer() {
    checkoutError = "";
    openPanel(drawerElement, drawerBackdrop);
    await loadDrawerData(false);
}

async function loadDrawerData(isQuiet) {
    // Fetch fresh stock and slot data every time the drawer opens
    if (!isQuiet) {
        drawerStatus = "loading";
        renderDrawer();
    }

    try {
        const results = await Promise.all([apiGet("/api/menu"), apiGet("/api/slots")]);
        const menuData = results[0];

        maxQtyPerItem = menuData.max_qty_per_item;
        slotData = results[1];

        syncCartWithMenu(menuData.items);
        chooseDefaultSlot();
        drawerStatus = "ready";
    } catch (error) {
        drawerStatus = "error";
        drawerErrorText = error.message;
    }

    renderDrawer();
}

function chooseDefaultSlot() {
    // Keep the student's pick if it is still open, otherwise use the next open slot
    const stillOpen = slotData.slots.some(function (slot) {
        return slot.id === selectedSlotId && !slot.is_full;
    });

    if (slotMode === "next" || !stillOpen) {
        selectedSlotId = slotData.next_open_slot_id;
    }
}


// =========================================================
// Drawing the drawer
// =========================================================

function renderDrawer() {
    // Re-drawing replaces the buttons, so remember which one had keyboard focus
    const focused = document.activeElement;
    const focusKey = focused && focused.dataset ? focused.dataset.focusKey : null;

    if (cartLines.length === 0) {
        cartBodyElement.innerHTML = buildEmptyCartHtml();
        cartFooterElement.innerHTML = "";
    } else {
        cartBodyElement.innerHTML = buildLinesHtml() + buildSlotSectionHtml() + buildPaymentHtml();
        cartFooterElement.innerHTML = buildFooterHtml();
    }

    drawIcons();

    if (focusKey) {
        const sameButton = drawerElement.querySelector('[data-focus-key="' + focusKey + '"]');
        if (sameButton && !sameButton.disabled) {
            sameButton.focus();
        }
    }
}

function buildEmptyCartHtml() {
    return `
      <div class="empty-state empty-state--compact">
        <i data-lucide="shopping-bag"></i>
        <h3>Your cart is empty</h3>
        <p class="text-soft">Add a dish from the menu and it will show up here.</p>
        <button class="btn btn--secondary" type="button" data-action="close-drawer">Back to the menu</button>
      </div>`;
}

function buildLinesHtml() {
    const rows = cartLines.map(function (line) {
        const atLimit = line.quantity >= getLineLimit(line);

        return `
          <li class="cart-line">
            <div class="cart-line__info">
              ${foodDotHtml(line.foodType)}
              <div>
                <p class="cart-line__name">${escapeHtml(line.name)}</p>
                <p class="cart-line__price num">${formatPrice(line.price)} each</p>
              </div>
            </div>
            <div class="stepper" role="group" aria-label="Quantity of ${escapeHtml(line.name)}">
              <button class="stepper__button" type="button" data-action="decrease" data-id="${line.itemId}"
                      data-focus-key="dec-${line.itemId}" aria-label="One less ${escapeHtml(line.name)}">−</button>
              <span class="stepper__value num" aria-live="polite">${line.quantity}</span>
              <button class="stepper__button" type="button" data-action="increase" data-id="${line.itemId}"
                      data-focus-key="inc-${line.itemId}" aria-label="One more ${escapeHtml(line.name)}"
                      ${atLimit ? "disabled" : ""}>+</button>
            </div>
            <button class="icon-button" type="button" data-action="remove" data-id="${line.itemId}"
                    data-focus-key="rm-${line.itemId}" aria-label="Remove ${escapeHtml(line.name)}">
              <i data-lucide="trash-2"></i>
            </button>
          </li>`;
    });

    return `<ul class="cart-lines">${rows.join("")}</ul>`;
}

function buildSlotSectionHtml() {
    let content = "";

    if (drawerStatus === "loading" || drawerStatus === "idle") {
        content = `
          <div class="skeleton skeleton--card" style="height: 64px;"></div>`;
    } else if (drawerStatus === "error") {
        content = `
          <div class="error-banner" role="alert">
            <i data-lucide="triangle-alert"></i>
            <span>${escapeHtml(drawerErrorText)}</span>
            <button class="btn btn--outline" type="button" data-action="retry-load">Try again</button>
          </div>`;
    } else if (slotData.slots.length === 0) {
        content = `
          <p class="empty-note">
            <i data-lucide="moon"></i>
            No pickup slots are left today. The canteen may be closed. Please try again tomorrow.
          </p>`;
    } else {
        content = buildSlotModeSwitchHtml() + (slotMode === "next" ? buildNextSlotHtml() : buildSlotGridHtml());
    }

    return `
      <section class="cart-section" aria-labelledby="slot-title">
        <h3 id="slot-title">Pickup time</h3>
        ${content}
      </section>`;
}

function buildSlotModeSwitchHtml() {
    return `
      <div class="segmented" role="group" aria-label="Pickup time choice">
        <button class="segmented__button ${slotMode === "next" ? "is-active" : ""}" type="button"
                data-action="mode-next" data-focus-key="mode-next" aria-pressed="${slotMode === "next"}">Next available</button>
        <button class="segmented__button ${slotMode === "later" ? "is-active" : ""}" type="button"
                data-action="mode-later" data-focus-key="mode-later" aria-pressed="${slotMode === "later"}">Later today</button>
      </div>`;
}

function buildNextSlotHtml() {
    const slot = slotData.slots.find(function (candidate) { return candidate.id === slotData.next_open_slot_id; });

    if (!slot) {
        return `<p class="empty-note"><i data-lucide="circle-alert"></i> Every remaining slot today is full. Please try again later.</p>`;
    }

    return `
      <div class="slot-summary">
        <i data-lucide="clock-3"></i>
        <div>
          <p class="slot-summary__time num">${slot.start_label} – ${slot.end_label}</p>
          <p class="text-small text-soft">${slot.spots_left} ${slot.spots_left === 1 ? "place" : "places"} left${slot.is_busy ? " · filling fast" : ""}</p>
        </div>
      </div>`;
}

function buildSlotGridHtml() {
    const buttons = slotData.slots.map(function (slot) {
        const isSelected = slot.id === selectedSlotId;
        const classes = "slot-button" + (isSelected ? " is-selected" : "") + (slot.is_busy ? " is-busy" : "");
        const note = slot.is_full ? "Full" : slot.is_busy ? "Filling fast" : slot.spots_left + " left";

        // Full slots are greyed out and cannot be tapped
        return `
          <button class="${classes}" type="button" data-action="pick-slot" data-id="${slot.id}"
                  data-focus-key="slot-${slot.id}" aria-pressed="${isSelected}" ${slot.is_full ? "disabled" : ""}>
            <span class="slot-button__time num">${slot.start_label}</span>
            <span class="slot-button__note">${note}</span>
          </button>`;
    });

    return `<div class="slot-grid">${buttons.join("")}</div>`;
}

function buildPaymentHtml() {
    return `
      <fieldset class="cart-section payment-options">
        <legend><h3>Payment</h3></legend>
        <label class="payment-option">
          <input type="radio" name="payment" value="mock_upi" ${paymentMethod === "mock_upi" ? "checked" : ""}>
          <span>
            <strong>UPI (demo)</strong>
            <small>A simulated payment. No real money is charged.</small>
          </span>
        </label>
        <label class="payment-option">
          <input type="radio" name="payment" value="counter" ${paymentMethod === "counter" ? "checked" : ""}>
          <span>
            <strong>Pay at the counter</strong>
            <small>Pay when you collect your order.</small>
          </span>
        </label>
      </fieldset>`;
}

function buildFooterHtml() {
    const canOrder = drawerStatus === "ready" && selectedSlotId !== null && !isPlacingOrder;
    let buttonText = "Place order · " + formatPrice(getCartTotal());

    if (isPlacingOrder) {
        buttonText = paymentMethod === "mock_upi" ? "Processing payment…" : "Placing your order…";
    }

    const errorHtml = checkoutError
        ? `<div class="error-banner" role="alert"><i data-lucide="triangle-alert"></i><span>${escapeHtml(checkoutError)}</span></div>`
        : "";

    return `
      ${errorHtml}
      <div class="drawer__total">
        <span>Total</span>
        <span class="num">${formatPrice(getCartTotal())}</span>
      </div>
      <button class="btn btn--primary btn--large btn--full" type="button" data-action="place-order"
              data-focus-key="place-order" ${canOrder ? "" : "disabled"}>${buttonText}</button>`;
}


// =========================================================
// Checkout
// =========================================================

function wait(milliseconds) {
    return new Promise(function (resolve) { setTimeout(resolve, milliseconds); });
}

async function placeOrder() {
    if (isPlacingOrder || cartLines.length === 0 || selectedSlotId === null) {
        return;
    }

    checkoutError = "";
    isPlacingOrder = true;
    renderDrawer();

    try {
        // The "UPI" payment is a simulation: we just pause so it feels like a real step
        if (paymentMethod === "mock_upi") {
            await wait(simulatedPaymentDelayMs);
        }

        const result = await apiPost("/api/orders", {
            items: cartLines.map(function (line) { return { item_id: line.itemId, quantity: line.quantity }; }),
            slot_id: selectedSlotId,
            payment_method: paymentMethod,
        });

        // Success: empty the cart and open the live tracker.
        // isPlacingOrder stays true so a second tap cannot create a second order.
        clearCart();
        window.location.href = result.order_url;
        return;
    } catch (error) {
        isPlacingOrder = false;
        checkoutError = error.message;

        // The slot filled up: switch to the server's suggested slot and ask for one more tap
        if (error.data && error.data.suggested_slot_id) {
            selectedSlotId = error.data.suggested_slot_id;
            slotMode = "next";
            checkoutError += " We picked the next open slot for you. Please check it and tap Place order again.";
        }
    }

    // Reload slots and stock so the drawer shows the truth, keeping the error message
    await loadDrawerData(true);
}


// =========================================================
// Clicks inside the drawer (one listener handles every button)
// =========================================================

drawerElement.addEventListener("click", function (event) {
    const button = event.target.closest("[data-action]");
    if (!button) {
        return;
    }

    const itemId = Number(button.dataset.id);

    switch (button.dataset.action) {
        case "increase":
            changeQuantity(itemId, 1);
            break;
        case "decrease":
            changeQuantity(itemId, -1);
            break;
        case "remove":
            removeLine(itemId);
            break;
        case "mode-next":
            slotMode = "next";
            chooseDefaultSlot();
            renderDrawer();
            break;
        case "mode-later":
            slotMode = "later";
            renderDrawer();
            break;
        case "pick-slot":
            selectedSlotId = itemId;
            checkoutError = "";
            renderDrawer();
            break;
        case "retry-load":
            loadDrawerData(false);
            break;
        case "place-order":
            placeOrder();
            break;
        case "close-drawer":
            closePanel();
            break;
    }
});

drawerElement.addEventListener("change", function (event) {
    if (event.target.name === "payment") {
        paymentMethod = event.target.value;
    }
});

document.getElementById("cart-open-button").addEventListener("click", openCartDrawer);
document.getElementById("cart-close-button").addEventListener("click", closePanel);
drawerBackdrop.addEventListener("click", closePanel);

const cartBarElement = document.getElementById("cart-bar");
if (cartBarElement) {
    cartBarElement.addEventListener("click", openCartDrawer);
}


// =========================================================
// Start
// =========================================================

loadCart();
updateCartDisplay(false);

// The small public toolbox other files can use
const Cart = {
    addItem: addItem,
    open: openCartDrawer,
    setMaxQty: function (value) { maxQtyPerItem = value; },
    getLine: findLine,
};
