/**
 * canteen.js - Vanilla JS controller for Qless Canteen Staff & Manager screens.
 *
 * Powers:
 *   1. Live Orders & Kitchen Queue (/canteen/orders) - 15s polling + 1-tap transitions
 *   2. Pickup Queue (/canteen/pickup) - 4-digit OTP & QR token lookup + handover
 *   3. Menu & Availability (/canteen/menu) - Batch qty, stock qty, Sold Out + Dish modal
 *   4. Shift Waste Entry (/canteen/waste) - Fast shift waste logging
 *   5. Manager Settings (/canteen/settings) - 15-min slot capacities + staff accounts
 */

(function () {
    "use strict";

    const shell = document.getElementById("canteen-shell");
    const pollSeconds = Number(shell ? shell.dataset.pollSeconds : 15) || 15;
    const syncLabel = document.getElementById("canteen-sync-label");
    const retryBanner = document.getElementById("canteen-retry-banner");

    function escapeHtml(value) {
        const div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function fetchJson(url, options) {
        return window.QlessCanteen.fetchJson(url, options);
    }

    function showToast(message, tone) {
        window.QlessCanteen.showToast(message, tone);
    }

    function refreshIcons() {
        window.QlessCanteen.refreshIcons();
    }

    // =========================================================
    // 1. Live Orders & Kitchen Queue (/canteen/orders)
    // =========================================================

    const ordersPage = document.getElementById("canteen-orders-page");

    function renderOrderBadge(order) {
        let html = "";
        if (order.status === "confirmed") {
            html = '<span class="canteen-badge canteen-badge--warning">Confirmed</span>';
        } else if (order.status === "preparing") {
            html = '<span class="canteen-badge canteen-badge--mint">Preparing</span>';
        } else if (order.status === "ready") {
            html = '<span class="canteen-badge canteen-badge--success">Ready for Pickup</span>';
        } else if (order.status === "collected") {
            html = '<span class="canteen-badge canteen-badge--forest">Collected</span>';
        }
        if (order.is_uncollected) {
            html += ' <span class="canteen-badge canteen-badge--urgent">Uncollected &gt;30m (' +
                order.minutes_since_ready + "m)</span>";
        }
        return html;
    }

    function renderOrderButton(order) {
        if (order.status === "confirmed") {
            return (
                '<button class="canteen-btn canteen-btn--primary js-order-status-btn" type="button" ' +
                'data-order-id="' + order.id + '" data-next-status="preparing">' +
                '<i data-lucide="play"></i><span>Start Prep</span></button>'
            );
        }
        if (order.status === "preparing") {
            return (
                '<button class="canteen-btn canteen-btn--leaf js-order-status-btn" type="button" ' +
                'data-order-id="' + order.id + '" data-next-status="ready">' +
                '<i data-lucide="check-circle-2"></i><span>Mark Ready</span></button>'
            );
        }
        if (order.status === "ready") {
            return (
                '<button class="canteen-btn canteen-btn--outline js-order-status-btn" type="button" ' +
                'data-order-id="' + order.id + '" data-next-status="collected">' +
                '<i data-lucide="package-check"></i><span>Mark Collected</span></button>'
            );
        }
        return '<span class="canteen-badge canteen-badge--mint">Handed Over</span>';
    }

    async function refreshLiveOrdersPage() {
        if (!ordersPage) {
            return;
        }
        const statusFilter = ordersPage.getAttribute("data-status-filter") || "all";
        try {
            const data = await fetchJson("/api/canteen/orders?status=" + encodeURIComponent(statusFilter));
            if (retryBanner) {
                retryBanner.hidden = true;
            }

            ["all", "confirmed", "preparing", "ready", "collected"].forEach(function (key) {
                const badge = document.getElementById("count-" + key);
                if (badge && data.counts && data.counts[key] != null) {
                    badge.textContent = data.counts[key];
                }
            });

            const container = document.getElementById("live-orders-container");
            if (!data.slot_groups || data.slot_groups.length === 0) {
                container.innerHTML =
                    '<div class="canteen-empty"><i data-lucide="inbox"></i>' +
                    '<h3 class="canteen-empty__title">No orders in this filter</h3>' +
                    '<p class="canteen-empty__text">Switch tabs above or wait for incoming student orders. ' +
                    "This queue refreshes every 15 seconds.</p></div>";
            } else {
                const groupsHtml = data.slot_groups.map(function (slot) {
                    const ordersHtml = slot.orders.map(function (order) {
                        const dishesHtml = order.items.map(function (item) {
                            return (
                                '<span class="dish-pill">' +
                                '<span class="food-dot food-dot--' + escapeHtml(item.food_type) + '"></span>' +
                                '<span class="dish-pill__qty">' + item.quantity + "&times;</span>" +
                                "<span>" + escapeHtml(item.name) + "</span></span>"
                            );
                        }).join("");

                        return (
                            '<div class="prep-row ' + (order.is_uncollected ? "prep-row--uncollected" : "") + '" ' +
                            'data-order-id="' + order.id + '">' +
                            '<div class="prep-row__id-col">' +
                            '<span class="prep-row__order-num">Order #' + order.id + "</span>" +
                            '<span class="prep-row__otp">OTP ' + escapeHtml(order.pickup_otp) + "</span></div>" +
                            '<div class="prep-row__details">' +
                            '<div class="prep-row__dishes">' + dishesHtml + "</div>" +
                            '<div class="prep-row__meta">' +
                            "<span><strong>" + escapeHtml(order.student_name) + "</strong> (" +
                            escapeHtml(order.campus_id) + ")</span><span>•</span>" +
                            "<span>" + escapeHtml(order.payment_method_label) + " (&#8377;" +
                            Math.round(order.total_amount) + ")</span><span>•</span>" +
                            "<span>Placed " + escapeHtml(order.created_label) + "</span><span>•</span>" +
                            renderOrderBadge(order) + "</div></div>" +
                            '<div class="prep-row__actions">' + renderOrderButton(order) + "</div></div>"
                        );
                    }).join("");

                    return (
                        '<section class="slot-group"><header class="slot-group__bar">' +
                        '<div class="slot-group__time"><i data-lucide="clock"></i>' +
                        "<span>" + escapeHtml(slot.slot_label) + "</span></div>" +
                        '<span class="canteen-badge canteen-badge--mint">' +
                        slot.orders.length + " order(s) in view • Cap " + slot.capacity + "</span></header>" +
                        '<div class="slot-group__orders">' + ordersHtml + "</div></section>"
                    );
                }).join("");

                container.innerHTML = '<div class="slot-group-list">' + groupsHtml + "</div>";
            }

            if (syncLabel && data.server_time) {
                syncLabel.textContent = "Synced " + data.server_time;
            }
            refreshIcons();
        } catch (error) {
            if (retryBanner) {
                retryBanner.hidden = false;
            }
        }
    }

    if (ordersPage) {
        document.addEventListener("click", async function (event) {
            const btn = event.target.closest(".js-order-status-btn");
            if (!btn) {
                return;
            }
            const orderId = btn.getAttribute("data-order-id");
            const nextStatus = btn.getAttribute("data-next-status");
            btn.disabled = true;
            try {
                const res = await fetchJson("/api/canteen/orders/" + orderId + "/status", {
                    method: "POST",
                    body: { next_status: nextStatus }
                });
                showToast(res.message, "success");
                await refreshLiveOrdersPage();
            } catch (error) {
                showToast(error.message, "error");
                btn.disabled = false;
            }
        });

        window.setInterval(refreshLiveOrdersPage, pollSeconds * 1000);
    }

    // =========================================================
    // 2. Pickup Queue / QR & 4-Digit OTP Verification (/canteen/pickup)
    // =========================================================

    const pickupPage = document.getElementById("canteen-pickup-page");

    function renderVerifiedOrderCard(order) {
        const dishesHtml = order.items.map(function (item) {
            return (
                '<span class="dish-pill">' +
                '<span class="food-dot food-dot--' + escapeHtml(item.food_type) + '"></span>' +
                '<span class="dish-pill__qty">' + item.quantity + "&times;</span>" +
                "<span>" + escapeHtml(item.name) + "</span></span>"
            );
        }).join("");

        const canCollect = order.status !== "collected" && order.status !== "cancelled";
        const actionHtml = canCollect
            ? (
                '<button class="canteen-btn canteen-btn--leaf js-collect-order-btn" type="button" ' +
                'data-order-id="' + order.id + '">' +
                '<i data-lucide="check-check"></i>' +
                "<span>Confirm Handover (Collected)</span></button>"
            )
            : '<span class="canteen-badge canteen-badge--forest">Already Collected</span>';

        return (
            '<div class="verify-result-card">' +
            '<div class="verify-result-card__top">' +
            "<div>" +
            '<div class="verify-result-card__otp">Order #' + order.id + " • OTP " +
            escapeHtml(order.pickup_otp) + "</div>" +
            '<div class="prep-row__meta">' +
            "<span><strong>" + escapeHtml(order.student_name) + "</strong> (" +
            escapeHtml(order.campus_id) + ")</span><span>•</span>" +
            "<span>Slot " + escapeHtml(order.slot_label) + "</span><span>•</span>" +
            "<span>" + escapeHtml(order.payment_method_label) + " (&#8377;" +
            Math.round(order.total_amount) + ")</span></div></div>" +
            actionHtml + "</div>" +
            '<div class="prep-row__dishes">' + dishesHtml + "</div></div>"
        );
    }

    if (pickupPage) {
        const verifyForm = document.getElementById("pickup-verify-form");
        const codeInput = document.getElementById("pickup-code-input");
        const resultBox = document.getElementById("pickup-verify-result");

        if (verifyForm) {
            verifyForm.addEventListener("submit", async function (event) {
                event.preventDefault();
                const code = (codeInput.value || "").trim();
                if (!code) {
                    return;
                }
                try {
                    const res = await fetchJson("/api/canteen/pickup/verify", {
                        method: "POST",
                        body: { code: code, action: "lookup" }
                    });
                    resultBox.innerHTML = renderVerifiedOrderCard(res.order);
                    resultBox.hidden = false;
                    refreshIcons();
                } catch (error) {
                    resultBox.hidden = true;
                    showToast(error.message, "error");
                }
            });
        }

        document.addEventListener("click", async function (event) {
            const collectBtn = event.target.closest(".js-collect-order-btn");
            if (!collectBtn) {
                return;
            }
            const orderId = collectBtn.getAttribute("data-order-id");
            collectBtn.disabled = true;
            try {
                const res = await fetchJson("/api/canteen/pickup/verify", {
                    method: "POST",
                    body: { action: "collect", order_id: Number(orderId) }
                });
                showToast(res.message, "success");
                window.setTimeout(function () {
                    window.location.reload();
                }, 450);
            } catch (error) {
                showToast(error.message, "error");
                collectBtn.disabled = false;
            }
        });
    }

    // =========================================================
    // 3. Menu, Stock & Prepared Batch Qty (/canteen/menu)
    // =========================================================

    const menuPage = document.getElementById("canteen-menu-page");

    if (menuPage) {
        const categoryTabs = document.getElementById("menu-category-tabs");
        const searchInput = document.getElementById("menu-search-input");
        let activeCategory = "all";

        function filterMenuRows() {
            const query = ((searchInput ? searchInput.value : "") || "").trim().toLowerCase();
            document.querySelectorAll("[data-dish-row]").forEach(function (row) {
                const rowCat = row.getAttribute("data-category");
                const rowName = row.getAttribute("data-name") || "";
                const matchesCat = activeCategory === "all" || rowCat === activeCategory;
                const matchesSearch = !query || rowName.indexOf(query) !== -1;
                row.hidden = !(matchesCat && matchesSearch);
            });
        }

        if (categoryTabs) {
            categoryTabs.addEventListener("click", function (event) {
                const tab = event.target.closest("[data-category]");
                if (!tab) {
                    return;
                }
                activeCategory = tab.getAttribute("data-category");
                categoryTabs.querySelectorAll(".filter-tab").forEach(function (btn) {
                    btn.classList.toggle("filter-tab--active", btn === tab);
                });
                filterMenuRows();
            });
        }

        if (searchInput) {
            searchInput.addEventListener("input", filterMenuRows);
        }

        function updateMenuRowUi(item) {
            const row = document.querySelector('[data-dish-row="' + item.id + '"]');
            if (!row) {
                return;
            }
            row.classList.toggle("is-sold-out-row", Boolean(item.is_sold_out));

            const stockInput = row.querySelector(".js-stock-input");
            const batchInput = row.querySelector(".js-batch-input");
            if (stockInput) {
                stockInput.value = item.stock_qty;
            }
            if (batchInput) {
                batchInput.value = item.prepared_batch_qty;
            }

            const statusCell = row.querySelector(".js-status-cell");
            if (statusCell) {
                if (item.is_sold_out) {
                    statusCell.innerHTML = '<span class="canteen-badge canteen-badge--error">Sold Out</span>';
                } else if (item.is_low_stock) {
                    statusCell.innerHTML = '<span class="canteen-badge canteen-badge--warning">Low Stock (&le;' +
                        item.stock_qty + ")</span>";
                } else {
                    statusCell.innerHTML = '<span class="canteen-badge canteen-badge--success">Available</span>';
                }
            }

            const toggleBtn = row.querySelector(".js-toggle-soldout-btn");
            if (toggleBtn) {
                toggleBtn.className = "canteen-btn canteen-btn--sm " +
                    (item.is_sold_out ? "canteen-btn--outline" : "canteen-btn--danger-outline") +
                    " js-toggle-soldout-btn";
                toggleBtn.innerHTML = "<span>" + (item.is_sold_out ? "Restock" : "Sold Out") + "</span>";
                toggleBtn.disabled = false;
            }
        }

        document.addEventListener("click", async function (event) {
            const saveBtn = event.target.closest(".js-save-stock-btn");
            if (saveBtn) {
                const itemId = saveBtn.getAttribute("data-item-id");
                const row = document.querySelector('[data-dish-row="' + itemId + '"]');
                const stockVal = row.querySelector(".js-stock-input").value;
                const batchVal = row.querySelector(".js-batch-input").value;
                saveBtn.disabled = true;

                try {
                    const res = await fetchJson("/api/canteen/menu/" + itemId + "/stock", {
                        method: "POST",
                        body: {
                            stock_qty: Number(stockVal),
                            prepared_batch_qty: Number(batchVal)
                        }
                    });
                    updateMenuRowUi(res.item);
                    showToast(res.message, "success");
                } catch (error) {
                    showToast(error.message, "error");
                } finally {
                    saveBtn.disabled = false;
                }
                return;
            }

            const toggleBtn = event.target.closest(".js-toggle-soldout-btn");
            if (toggleBtn) {
                const itemId = toggleBtn.getAttribute("data-item-id");
                toggleBtn.disabled = true;
                try {
                    const res = await fetchJson("/api/canteen/menu/" + itemId + "/stock", {
                        method: "POST",
                        body: { action: "toggle_sold_out" }
                    });
                    updateMenuRowUi(res.item);
                    showToast(res.message, res.item.is_sold_out ? "warning" : "success");
                } catch (error) {
                    showToast(error.message, "error");
                    toggleBtn.disabled = false;
                }
                return;
            }

            const editBtn = event.target.closest(".js-edit-dish-btn");
            if (editBtn) {
                const itemId = editBtn.getAttribute("data-item-id");
                const row = document.querySelector('[data-dish-row="' + itemId + '"]');
                const backdrop = document.getElementById("dish-modal-backdrop");
                if (!row || !backdrop) {
                    return;
                }

                document.getElementById("dish-modal-title").textContent = "Edit Menu Dish";
                document.getElementById("dish-id-field").value = row.getAttribute("data-dish-id") || "";
                document.getElementById("dish-name-field").value = row.getAttribute("data-dish-title") || "";
                document.getElementById("dish-desc-field").value = row.getAttribute("data-dish-desc") || "";
                document.getElementById("dish-category-field").value = row.getAttribute("data-dish-category") || "Meals";
                document.getElementById("dish-food-type-field").value = row.getAttribute("data-dish-food-type") || "veg";
                document.getElementById("dish-price-field").value = Math.round(Number(row.getAttribute("data-dish-price") || 0));
                document.getElementById("dish-prep-field").value = row.getAttribute("data-dish-prep") || "10";
                document.getElementById("dish-batch-field").value = row.querySelector(".js-batch-input").value;
                document.getElementById("dish-stock-field").value = row.querySelector(".js-stock-input").value;
                document.getElementById("dish-allergens-field").value = row.getAttribute("data-dish-allergens") || "";
                document.getElementById("dish-featured-field").checked = row.getAttribute("data-dish-featured") === "1";

                backdrop.hidden = false;
            }
        });

        const openAddBtn = document.getElementById("open-add-dish-btn");
        const closeDishBtn = document.getElementById("close-dish-modal-btn");
        const cancelDishBtn = document.getElementById("cancel-dish-modal-btn");
        const dishBackdrop = document.getElementById("dish-modal-backdrop");
        const dishForm = document.getElementById("manager-dish-form");

        function closeDishModal() {
            if (dishBackdrop) {
                dishBackdrop.hidden = true;
            }
        }

        if (openAddBtn && dishBackdrop && dishForm) {
            openAddBtn.addEventListener("click", function () {
                dishForm.reset();
                document.getElementById("dish-modal-title").textContent = "Add New Menu Dish";
                document.getElementById("dish-id-field").value = "";
                dishBackdrop.hidden = false;
            });
        }
        if (closeDishBtn) {
            closeDishBtn.addEventListener("click", closeDishModal);
        }
        if (cancelDishBtn) {
            cancelDishBtn.addEventListener("click", closeDishModal);
        }

        if (dishForm) {
            dishForm.addEventListener("submit", async function (event) {
                event.preventDefault();
                const payload = {
                    id: document.getElementById("dish-id-field").value || null,
                    name: document.getElementById("dish-name-field").value,
                    description: document.getElementById("dish-desc-field").value,
                    category: document.getElementById("dish-category-field").value,
                    food_type: document.getElementById("dish-food-type-field").value,
                    price: Number(document.getElementById("dish-price-field").value),
                    prep_time_minutes: Number(document.getElementById("dish-prep-field").value),
                    prepared_batch_qty: Number(document.getElementById("dish-batch-field").value),
                    stock_qty: Number(document.getElementById("dish-stock-field").value),
                    allergens: document.getElementById("dish-allergens-field").value,
                    is_featured: document.getElementById("dish-featured-field").checked ? 1 : 0,
                    is_active: 1
                };
                try {
                    const res = await fetchJson("/api/canteen/menu/save", {
                        method: "POST",
                        body: payload
                    });
                    showToast(res.message, "success");
                    closeDishModal();
                    window.setTimeout(function () {
                        window.location.reload();
                    }, 400);
                } catch (error) {
                    showToast(error.message, "error");
                }
            });
        }
    }

    // =========================================================
    // 4. Shift Waste Entry (/canteen/waste)
    // =========================================================

    const wastePage = document.getElementById("canteen-waste-page");

    if (wastePage) {
        const wasteForm = document.getElementById("waste-entry-form");
        const submitBtn = document.getElementById("waste-submit-btn");

        if (wasteForm) {
            wasteForm.addEventListener("submit", async function (event) {
                event.preventDefault();
                if (submitBtn) {
                    submitBtn.disabled = true;
                }

                const formData = new FormData(wasteForm);
                const payload = {
                    menu_item_id: formData.get("menu_item_id"),
                    quantity_wasted: formData.get("quantity_wasted"),
                    weight_kg: formData.get("weight_kg"),
                    reason: formData.get("reason"),
                    notes: formData.get("notes"),
                    waste_date: formData.get("waste_date")
                };

                try {
                    const res = await fetchJson("/api/canteen/waste", {
                        method: "POST",
                        body: payload
                    });
                    showToast(res.message, "success");
                    window.setTimeout(function () {
                        window.location.reload();
                    }, 450);
                } catch (error) {
                    showToast(error.message, "error");
                    if (submitBtn) {
                        submitBtn.disabled = false;
                    }
                }
            });
        }
    }

    // =========================================================
    // 5. Manager Settings (/canteen/settings)
    // =========================================================

    const settingsPage = document.getElementById("canteen-settings-page");

    if (settingsPage) {
        const bulkForm = document.getElementById("bulk-slot-capacity-form");
        const staffForm = document.getElementById("create-staff-form");

        if (bulkForm) {
            bulkForm.addEventListener("submit", async function (event) {
                event.preventDefault();
                const capacity = Number(document.getElementById("bulk-capacity-input").value);
                try {
                    const res = await fetchJson("/api/canteen/settings/slots", {
                        method: "POST",
                        body: { capacity: capacity }
                    });
                    showToast(res.message, "success");
                    window.setTimeout(function () {
                        window.location.reload();
                    }, 450);
                } catch (error) {
                    showToast(error.message, "error");
                }
            });
        }

        document.addEventListener("click", async function (event) {
            const slotBtn = event.target.closest(".js-save-slot-btn");
            if (!slotBtn) {
                return;
            }
            const slotId = slotBtn.getAttribute("data-slot-id");
            const input = document.querySelector('.js-slot-cap-input[data-slot-id="' + slotId + '"]');
            if (!input) {
                return;
            }
            slotBtn.disabled = true;
            try {
                const res = await fetchJson("/api/canteen/settings/slots", {
                    method: "POST",
                    body: { slot_id: Number(slotId), capacity: Number(input.value) }
                });
                showToast(res.message, "success");
            } catch (error) {
                showToast(error.message, "error");
            } finally {
                slotBtn.disabled = false;
            }
        });

        if (staffForm) {
            staffForm.addEventListener("submit", async function (event) {
                event.preventDefault();
                const formData = new FormData(staffForm);
                const payload = {
                    full_name: formData.get("full_name"),
                    email: formData.get("email"),
                    campus_id: formData.get("campus_id"),
                    role: formData.get("role"),
                    password: formData.get("password")
                };
                try {
                    const res = await fetchJson("/api/canteen/settings/staff", {
                        method: "POST",
                        body: payload
                    });
                    showToast(res.message, "success");
                    window.setTimeout(function () {
                        window.location.reload();
                    }, 450);
                } catch (error) {
                    showToast(error.message, "error");
                }
            });
        }
    }
})();
