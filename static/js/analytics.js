/**
 * analytics.js - Renders the Chart.js operational charts for Qless Phase 7.
 *
 * Reads the server-computed JSON from #analytics-payload-json and renders:
 *   1. Orders by 15-Minute Pickup Slot (Bar)
 *   2. Top-Selling Dishes (Horizontal Bar)
 *   3. Prepared vs. Sold by Item (Grouped Bar)
 *   4. Daily Food-Waste Trend (Line + Area)
 *   5. Food Waste by Dish (Bar)
 *   6. Waste Reason Breakdown (Doughnut)
 *   8. Category Demand vs. Waste Summary (Grouped Bar)
 */

(function () {
    "use strict";

    const payloadTag = document.getElementById("analytics-payload-json");
    if (!payloadTag || typeof window.Chart === "undefined") {
        return;
    }

    let chartsData = null;
    try {
        chartsData = JSON.parse(payloadTag.textContent);
    } catch (error) {
        return;
    }

    // Fresh Harvest Tech colour palette
    const COLOR_FOREST = "#064E3B";
    const COLOR_LEAF = "#16A34A";
    const COLOR_HONEY = "#D97706";
    const COLOR_TANGERINE = "#F97316";
    const COLOR_ERROR = "#DC2626";
    const COLOR_MINT_FILL = "rgba(22, 163, 74, 0.16)";
    const COLOR_TANGERINE_FILL = "rgba(249, 115, 22, 0.18)";

    window.Chart.defaults.font.family = '"Inter", "Segoe UI", Arial, sans-serif';
    window.Chart.defaults.color = "#4B5563";

    function makeChart(canvasId, config) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) {
            return null;
        }
        return new window.Chart(canvas, config);
    }

    // 1. Orders by 15-Minute Pickup Slot
    if (chartsData.orders_by_slot) {
        makeChart("chart-orders-by-slot", {
            type: "bar",
            data: {
                labels: chartsData.orders_by_slot.labels,
                datasets: [
                    {
                        label: "Orders Booked",
                        data: chartsData.orders_by_slot.orders,
                        backgroundColor: COLOR_FOREST,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    // 2. Top-Selling Dishes
    if (chartsData.top_dishes) {
        makeChart("chart-top-dishes", {
            type: "bar",
            data: {
                labels: chartsData.top_dishes.labels,
                datasets: [
                    {
                        label: "Portions Sold",
                        data: chartsData.top_dishes.portions,
                        backgroundColor: COLOR_LEAF,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    // 3. Prepared vs. Sold by Item
    if (chartsData.prepared_vs_sold) {
        makeChart("chart-prepared-vs-sold", {
            type: "bar",
            data: {
                labels: chartsData.prepared_vs_sold.labels,
                datasets: [
                    {
                        label: "Prepared Batch (Portions)",
                        data: chartsData.prepared_vs_sold.prepared,
                        backgroundColor: COLOR_HONEY,
                        borderRadius: 6
                    },
                    {
                        label: "Sold (Portions)",
                        data: chartsData.prepared_vs_sold.sold,
                        backgroundColor: COLOR_LEAF,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    // 4. Daily Food-Waste Trend
    if (chartsData.daily_waste_trend) {
        makeChart("chart-daily-waste", {
            type: "line",
            data: {
                labels: chartsData.daily_waste_trend.labels,
                datasets: [
                    {
                        label: "Portions Wasted",
                        data: chartsData.daily_waste_trend.portions,
                        borderColor: COLOR_TANGERINE,
                        backgroundColor: COLOR_TANGERINE_FILL,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4
                    },
                    {
                        label: "Weight (kg)",
                        data: chartsData.daily_waste_trend.weight_kg,
                        borderColor: COLOR_FOREST,
                        backgroundColor: COLOR_MINT_FILL,
                        fill: false,
                        tension: 0.3,
                        pointRadius: 3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true }
                }
            }
        });
    }

    // 5. Food Waste by Dish
    if (chartsData.waste_by_dish) {
        makeChart("chart-waste-by-dish", {
            type: "bar",
            data: {
                labels: chartsData.waste_by_dish.labels,
                datasets: [
                    {
                        label: "Portions Wasted",
                        data: chartsData.waste_by_dish.portions,
                        backgroundColor: COLOR_TANGERINE,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }

    // 6. Waste Reason Breakdown
    if (chartsData.waste_reasons) {
        makeChart("chart-waste-reasons", {
            type: "doughnut",
            data: {
                labels: chartsData.waste_reasons.labels,
                datasets: [
                    {
                        data: chartsData.waste_reasons.portions,
                        backgroundColor: [COLOR_HONEY, COLOR_ERROR, COLOR_TANGERINE],
                        borderWidth: 2,
                        borderColor: "#FFFFFF"
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%"
            }
        });
    }

    // 8. Category Demand vs. Waste Summary
    if (chartsData.category_performance) {
        makeChart("chart-category-summary", {
            type: "bar",
            data: {
                labels: chartsData.category_performance.labels,
                datasets: [
                    {
                        label: "Portions Sold",
                        data: chartsData.category_performance.sold,
                        backgroundColor: COLOR_FOREST,
                        borderRadius: 6
                    },
                    {
                        label: "Portions Wasted",
                        data: chartsData.category_performance.wasted,
                        backgroundColor: COLOR_ERROR,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, ticks: { precision: 0 } }
                }
            }
        });
    }
})();
