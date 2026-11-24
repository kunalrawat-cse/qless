/*
  menu.js - The student menu page.

  What happens here:
    1. Show grey loading cards while the menu loads
    2. Fetch /api/menu (dishes + live stock) and /api/slots (for "next pickup")
    3. Draw the "Ready fast" strip, category chips and the food grid
    4. Filter by search text, category and Veg / Non-veg / Egg
    5. Open the Food Details modal; "+ Add" puts a dish in the cart (cart.js)

  Safe things to edit later:
    - categoryIcons: the icon shown on a dish that has no photo
    - menuRefreshSeconds: how often stock is refreshed in the background
*/

const categoryIcons = {
    "Breakfast": "sunrise",
    "Meals": "utensils",
    "Snacks": "cookie",
    "Rolls & Wraps": "sandwich",
    "Beverages": "coffee",
};
const menuRefreshSeconds = 30;

// ---------- Page state ----------

let allItems = [];
let categoryNames = [];
let slotInfo = null;
let activeCategory = "all";
let dietFilter = "all";
let searchText = "";
let hasAppliedDietPreference = false;
let lastMenuSnapshot = "";

const gridElement = document.getElementById("food-grid");
const featuredSection = document.getElementById("featured-section");
const featuredStrip = document.getElementById("featured-strip");
const chipsElement = document.getElementById("category-chips");
const errorBox = document.getElementById("menu-error");
const modalElement = document.getElementById("food-modal");
const modalBackdrop = document.getElementById("food-backdrop");
const modalBody = document.getElementById("food-modal-body");


// =========================================================
// Loading
// =========================================================

function showLoadingCards() {
    // Six shimmering placeholders while the first load runs
    const placeholder = '<div class="food-card food-card--skeleton skeleton" aria-hidden="true"></div>';
    gridElement.innerHTML = placeholder.repeat(6);
    chipsElement.innerHTML = '<div class="skeleton" style="width: 100%; height: 36px;"></div>';
}

async function loadMenu(isBackgroundRefresh) {
    try {
        const results = await Promise.all([apiGet("/api/menu"), apiGet("/api/slots")]);
        const menuData = results[0];

        // A quiet refresh does nothing if nothing changed (so keyboard focus is not lost)
        const snapshot = JSON.stringify([menuData.items, results[1].next_open_slot_id]);
        if (isBackgroundRefresh && snapshot === lastMenuSnapshot) {
            return;
        }
        lastMenuSnapshot = snapshot;

        allItems = menuData.items;
        categoryNames = menuData.categories;
        slotInfo = results[1];
        Cart.setMaxQty(menuData.max_qty_per_item);

        // Start with the student's own dietary preference selected (only once)
        if (!hasAppliedDietPreference) {
            hasAppliedDietPreference = true;
            if (["veg", "non_veg", "egg"].includes(menuData.dietary_preference)) {
                dietFilter = menuData.dietary_preference;
            }
        }

        errorBox.hidden = true;
        renderMenu();
    } catch (error) {
        // Do not wipe a menu that is already on screen because of one failed refresh
        if (isBackgroundRefresh && allItems.length > 0) {
            return;
        }
        gridElement.innerHTML = "";
        featuredSection.hidden = true;
        chipsElement.innerHTML = "";
        document.getElementById("menu-error-text").textContent = error.message;
        errorBox.hidden = false;
        drawIcons();
    }
}


// =========================================================
// Filtering
// =========================================================

function getVisibleItems() {
    const text = searchText.trim().toLowerCase();

    const matches = allItems.filter(function (item) {
        if (activeCategory !== "all" && item.category !== activeCategory) {
            return false;
        }
        if (dietFilter !== "all" && item.food_type !== dietFilter) {
            return false;
        }
        if (text !== "") {
            const searchable = (item.name + " " + item.description + " " + item.category).toLowerCase();
            return searchable.includes(text);
        }
        return true;
    });

    // Sold-out dishes drop to the bottom of the list
    return matches.sort(function (a, b) {
        return Number(b.available) - Number(a.available) || a.name.localeCompare(b.name);
    });
}

function isFilterActive() {
    return activeCategory !== "all" || dietFilter !== "all" || searchText.trim() !== "";
}


// =========================================================
// Drawing
// =========================================================

function renderMenu() {
    renderCategoryChips();
    renderDietChips();
    renderFeatured();
    renderGrid();
    drawIcons();
}

function renderCategoryChips() {
    const chips = ["all"].concat(categoryNames).map(function (name) {
        const label = name === "all" ? "All" : name;
        const activeClass = name === activeCategory ? " chip--active" : "";
        return `<button class="chip${activeClass}" type="button" data-category="${escapeHtml(name)}"
                        aria-pressed="${name === activeCategory}">${escapeHtml(label)}</button>`;
    });

    chipsElement.innerHTML = chips.join("");
}

function renderDietChips() {
    document.querySelectorAll("#diet-filter .chip").forEach(function (chip) {
        const isActive = chip.dataset.diet === dietFilter;
        chip.classList.toggle("chip--active", isActive);
        chip.setAttribute("aria-pressed", String(isActive));
    });
}

function renderFeatured() {
    // The strip only shows on the unfiltered menu, so search results are not crowded
    const featuredItems = allItems.filter(function (item) {
        return item.is_featured && item.available && (dietFilter === "all" || item.food_type === dietFilter);
    });

    const shouldShow = featuredItems.length > 0 && activeCategory === "all" && searchText.trim() === "";
    featuredSection.hidden = !shouldShow;

    featuredStrip.innerHTML = featuredItems.map(function (item) {
        return buildFoodCardHtml(item, true);
    }).join("");
}

function renderGrid() {
    const items = getVisibleItems();

    if (items.length === 0) {
        gridElement.innerHTML = `
          <div class="empty-state">
            <i data-lucide="search-x"></i>
            <h3>No dishes found</h3>
            <p class="text-soft">Try a different word, or clear the filters.</p>
            ${isFilterActive() ? '<button class="btn btn--secondary" type="button" data-action="clear-filters">Clear filters</button>' : ""}
          </div>`;
        return;
    }

    gridElement.innerHTML = items.map(function (item) {
        return buildFoodCardHtml(item, false);
    }).join("");
}

function buildPhotoHtml(item) {
    // A dish with a photo shows it; a dish without one (or whose file fails to load) shows its category icon.
    const icon = categoryIcons[item.category] || "utensils";
    if (item.image_url) {
        return `<img src="${escapeHtml(item.image_url)}" alt="" loading="lazy" decoding="async" width="600" height="400" data-fallback-icon="${icon}">`;
    }
    return `<i data-lucide="${icon}"></i>`;
}

// If a photo is missing or broken, swap it for the category icon so the card never shows a broken image.
document.addEventListener("error", function (event) {
    const image = event.target;
    if (!(image instanceof HTMLImageElement) || !image.dataset.fallbackIcon) {
        return;
    }
    const holder = image.parentElement;
    holder.classList.add("is-fallback");
    holder.innerHTML = `<i data-lucide="${image.dataset.fallbackIcon}"></i>`;
    drawIcons();
}, true);

function buildStockBadgeHtml(item) {
    // Shown only for "Sold out" and "5 or fewer left", as the blueprint says
    if (!item.available) {
        return '<span class="badge badge--error">Sold out</span>';
    }
    if (item.low_stock) {
        return `<span class="badge badge--warning badge--low-stock">Only ${item.stock_qty} left</span>`;
    }
    return "";
}

function buildFoodCardHtml(item, isCompact) {
    const cardClasses = "food-card" + (isCompact ? " food-card--compact" : "") + (item.available ? "" : " is-sold-out");

    return `
      <article class="${cardClasses}">
        <button class="food-card__open" type="button" data-action="details" data-id="${item.id}"
                aria-label="View details of ${escapeHtml(item.name)}">
          <span class="food-card__photo">${buildPhotoHtml(item)}</span>
          <span class="food-card__info">
            <span class="food-card__name">${foodDotHtml(item.food_type)} ${escapeHtml(item.name)}</span>
            <span class="food-card__meta"><i data-lucide="clock-3"></i> ~${item.prep_time_minutes} min</span>
            ${buildStockBadgeHtml(item)}
          </span>
        </button>
        <div class="food-card__buy">
          <span class="food-card__price num">${formatPrice(item.price)}</span>
          <button class="btn btn--primary food-card__add" type="button" data-action="add" data-id="${item.id}"
                  aria-label="Add ${escapeHtml(item.name)} to cart" ${item.available ? "" : "disabled"}>+ Add</button>
        </div>
      </article>`;
}


// =========================================================
// Adding to the cart
// =========================================================

function findItem(itemId) {
    return allItems.find(function (item) { return item.id === itemId; });
}

function addToCartFromButton(button, item) {
    const wasAdded = Cart.addItem(item);
    if (!wasAdded) {
        return;
    }

    // "+ Add" turns into "✓ Added" for a moment
    button.classList.add("is-added");
    button.innerHTML = '<i data-lucide="check"></i> Added';
    drawIcons();

    setTimeout(function () {
        button.classList.remove("is-added");
        button.textContent = "+ Add";
    }, 1200);
}


// =========================================================
// Food details modal
// =========================================================

function buildModalHtml(item) {
    const inCart = Cart.getLine(item.id);

    let stockText = "In stock";
    if (!item.available) {
        stockText = "Sold out";
    } else if (item.low_stock) {
        stockText = "Only " + item.stock_qty + " left";
    }

    const nextPickup = slotInfo && slotInfo.next_open_slot_id
        ? slotInfo.slots.find(function (slot) { return slot.id === slotInfo.next_open_slot_id; }).start_label
        : "No slots left today";

    const ratingRow = item.average_rating !== null
        ? `<div><dt>Rating</dt><dd><i data-lucide="star"></i> <span class="num">${item.average_rating}</span> (${item.rating_count})</dd></div>`
        : "";

    // We list the allergens we know about. We never claim a dish is "allergen free".
    const allergenHtml = item.allergens.length > 0
        ? item.allergens.map(function (name) { return `<span class="tag">${escapeHtml(name)}</span>`; }).join("")
        : '<span class="text-small text-soft">No allergens listed</span>';

    return `
      <div class="modal__photo">${buildPhotoHtml(item)}</div>
      <div class="modal__content">
        <div class="modal__top">
          <h2 id="food-modal-title">${foodDotHtml(item.food_type)} ${escapeHtml(item.name)}</h2>
          <span class="modal__price num">${formatPrice(item.price)}</span>
        </div>
        <p class="text-soft">${escapeHtml(item.description)}</p>

        <dl class="detail-list">
          <div><dt>Prep time</dt><dd>~${item.prep_time_minutes} min</dd></div>
          <div><dt>Availability</dt><dd>${stockText}</dd></div>
          <div><dt>Next pickup</dt><dd class="num">${nextPickup}</dd></div>
          ${ratingRow}
        </dl>

        <h3 class="modal__subtitle">Allergens</h3>
        <div class="tag-row">${allergenHtml}</div>

        ${inCart ? `<p class="text-small text-soft">Already in your cart: <span class="num">${inCart.quantity}</span></p>` : ""}

        <button class="btn btn--primary btn--large btn--full" type="button" data-action="add-from-modal"
                data-id="${item.id}" ${item.available ? "" : "disabled"}>
          ${item.available ? "Add to cart · " + formatPrice(item.price) : "Sold out"}
        </button>
      </div>`;
}

function openFoodModal(item) {
    modalBody.innerHTML = buildModalHtml(item);
    drawIcons();
    openPanel(modalElement, modalBackdrop);
}


// =========================================================
// Events
// =========================================================

// Clicks on the food grid and the featured strip (one listener each)
function handleFoodClick(event) {
    const button = event.target.closest("[data-action]");
    if (!button) {
        return;
    }

    if (button.dataset.action === "clear-filters") {
        activeCategory = "all";
        dietFilter = "all";
        searchText = "";
        document.getElementById("menu-search").value = "";
        renderMenu();
        return;
    }

    const item = findItem(Number(button.dataset.id));
    if (!item) {
        return;
    }

    if (button.dataset.action === "add") {
        addToCartFromButton(button, item);
    } else if (button.dataset.action === "details") {
        openFoodModal(item);
    }
}

gridElement.addEventListener("click", handleFoodClick);
featuredStrip.addEventListener("click", handleFoodClick);

// "Add to cart" inside the modal
modalElement.addEventListener("click", function (event) {
    const button = event.target.closest('[data-action="add-from-modal"]');
    if (!button) {
        return;
    }

    const item = findItem(Number(button.dataset.id));
    if (item && Cart.addItem(item)) {
        showToast(item.name + " added to your cart.", "success");
        closePanel();
    }
});

document.getElementById("food-modal-close").addEventListener("click", closePanel);
modalBackdrop.addEventListener("click", closePanel);

// Category chips
chipsElement.addEventListener("click", function (event) {
    const chip = event.target.closest("[data-category]");
    if (!chip) {
        return;
    }
    activeCategory = chip.dataset.category;
    renderMenu();
});

// Veg / Non-veg / Egg chips
document.getElementById("diet-filter").addEventListener("click", function (event) {
    const chip = event.target.closest("[data-diet]");
    if (!chip) {
        return;
    }
    dietFilter = chip.dataset.diet;
    renderMenu();
});

// Search box: filters as you type
document.getElementById("menu-search").addEventListener("input", function (event) {
    searchText = event.target.value;
    renderMenu();
});

document.getElementById("menu-retry").addEventListener("click", function () {
    showLoadingCards();
    loadMenu(false);
});


// =========================================================
// Start
// =========================================================

showLoadingCards();
loadMenu(false);

// Keep sold-out and low-stock badges fresh while the page stays open
setInterval(function () {
    if (!document.hidden) {
        loadMenu(true);
    }
}, menuRefreshSeconds * 1000);
