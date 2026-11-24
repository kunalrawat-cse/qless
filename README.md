# Qless

**Smart Campus Canteen & Food-Waste Optimisation Platform**  
*Less Waiting. Less Waste. Better Campus.*

Theme: **Fresh Harvest Tech** (`#064E3B` Deep Forest • `#16A34A` Leaf Green • `#F97316` Citrus Tangerine • `#FAFDFB` Alabaster • `Outfit` + `Inter` • `Lucide Icons`)

Stack: **Python Flask + MySQL (`PyMySQL`) + Jinja2 Templates + Vanilla JS (`15s fetch()` polling) + Pandas / NumPy + Chart.js + Matplotlib (`Agg` PNG reports)**.

---

## Quick Start (VS Code Terminal)

1. **Create and activate your virtual environment:**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Configure `.env`:**
   Copy `.env.example` to `.env` and fill in your local MySQL credentials (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME=qless_db`).
3. **Initialize schema & demo seed data (if starting fresh):**
   Run `sql/schema.sql` and `sql/seed.sql` in MySQL Workbench or via the MySQL CLI.
4. **Start the server:**
   ```bash
   python app.py
   ```
   Open **`http://127.0.0.1:5000`** in your browser.

---

## Build Progress (All 8 Phases Complete)

- **Phase 1:** Project setup, Git, virtual environment, `.env` configuration *(done)*
- **Phase 2:** MySQL relational schema (`sql/schema.sql`), constraints, seed data & 14-day history *(done)*
- **Phase 3:** Backend core (`db.py`), session auth, CSRF protection, role decorators & 6-digit OTP password recovery *(done)*
- **Phase 4:** Fresh Harvest Tech design tokens (`variables.css`) & 4-page public showcase (`Home`, `How It Works`, `Sustainability`, `About/Contact`) *(done)*
- **Phase 5A:** Student menu, category/dietary filters, smart-default 15-minute pickup slots, transactional checkout (`SELECT ... FOR UPDATE`), live order tracker, QR + 4-digit OTP pickup card with `localStorage` offline fallback *(done)*
- **Phase 5B:** Student notification drawer, order history, 1-tap post-pickup star rating/feedback, profile & dietary settings *(done)*
- **Phase 6A & 6B:** Canteen Staff & Manager platform — collapsible sidebar (`Rush-Hour Ops` vs. `Post-Rush & Admin`), Layout A Split-Command Dashboard, slot-grouped Live Orders queue, Counter QR/OTP verification, Menu availability & Today's Prepared Batch Qty editor, Shift Waste Entry, and Manager Settings *(done)*
- **Phase 7:** Post-Rush Demand & Food-Waste Analytics (`analytics/reports.py`) — Pandas/NumPy aggregations, 8 Chart.js operational visualizations + 15-minute Slot Utilization Heatmap, Historical Orders table, Pandas CSV exports, and Matplotlib 2×2 executive PNG report download *(done)*
- **Phase 8:** Final security cleanup (`/db-check` removed), unified profile & password settings (`/account`), and 5-minute live demo walkthrough *(done)*

---

## 5-Minute Live Demo Walkthrough Script

### Step 1 — Public Product Showcase (45 seconds)
1. Open **`http://127.0.0.1:5000/`** (*Home*), **`/how-it-works`**, and **`/sustainability`**.
2. Point out the core problem Qless solves: **rush-hour queue congestion** (solved via capacity-capped 15-minute pickup slots) and **kitchen overproduction waste** (solved via pre-order item batching + *Prepared vs. Sold* analytics).

### Step 2 — Student Pre-Order, 15-Minute Pickup Slot & QR/OTP (90 seconds)
1. Click **Log in** and sign in with a **Student** account.
2. Filter the menu by category or dietary chip (*Veg*, *Non-Veg*, *Egg*), add 2–3 dishes to the cart, and open the **Cart Drawer**.
3. Show the **15-Minute Pickup Slot Selector** (which automatically defaults to the *Next Available Slot* and displays live slot load %).
4. Choose **Simulated UPI** or **Pay at Counter** and place the order.
5. On the **Live Order Tracker** page (`/orders/<id>`), highlight:
   - The **4-step status progress bar** (`Confirmed → Preparing → Ready for Pickup → Collected`) polling every 15 seconds.
   - The **Pickup Pass Card** displaying the **QR Token** and **4-Digit Pickup OTP** (cached in `localStorage` so students can still show their pass even if campus Wi-Fi drops).

### Step 3 — Canteen Rush-Hour "Action Now" Operations (90 seconds)
1. In a second browser window (or after logging out), sign in as **Kitchen / Counter Staff** or **Canteen Manager** at **`/login?as=staff`**.
2. On **`/canteen/dashboard` (Layout A — Split Command)**, highlight:
   - **Top Row (4 Action-Now KPIs):** `Orders Right Now`, `Orders in Next 15 Minutes`, `Pickup-Slot Load (%)`, and `Low-Stock / Unavailable Alerts`.
   - **Left 65% (Live Preparation Queue):** Orders grouped by 15-minute pickup window. Click **`Start Prep`** (`Confirmed → Preparing`), then click **`Mark Ready`** (`Preparing → Ready for Pickup`, which automatically sends a notification to the student).
   - **Right 35% (Item Batching, Quick Stock & Alerts):** Show aggregated dish prep counts for the next 15-minute wave and click **`Sold Out`** on a dish (dims row to 60% and disables student ordering immediately).
3. Open **`/canteen/pickup` (Pickup Queue / QR & OTP Verification)**:
   - Type the student's **4-digit Pickup OTP** into the verification box and click **`Verify Code`**.
   - Click **`Confirm Handover (Collected)`** to complete the order.

### Step 4 — Post-Rush Batch Tracking, Waste Entry & 8 Analytics Charts (75 seconds)
1. Open **`/canteen/menu`** and update **"Today's Prepared Batch Qty"** for a dish (syncs to `daily_batches`).
2. Open **`/canteen/waste`** and log an end-of-shift waste entry (`Overproduction`, `Spoilage`, or `Uncollected`).
3. Open **`/canteen/analytics`**:
   - Walk through the **4 Post-Rush KPIs** and the **8 Operational Charts** (*Orders by 15-Minute Slot*, *Top-Selling Dishes*, *Prepared vs. Sold by Item*, *Daily Food-Waste Trend*, *Food Waste by Dish*, *Waste Reason Breakdown*, *15-Minute Slot Utilization Heatmap*, and *Category Demand vs. Waste Summary*).
   - Click **`Orders CSV`**, **`Waste Logs CSV`**, and **`Download Report Chart (PNG)`** to demonstrate instant data and Matplotlib report exports.
4. Open **`/canteen/settings`** (as **Canteen Manager**) to show 15-minute slot capacity controls and staff account creation.
