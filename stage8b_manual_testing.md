# Servora — Stage 8B: Manual Walkthrough & Verification Guide

This guide walks through testing the complete **Stage 8B: UPI-Only Payment & Dynamic Job Pricing** flow on your local development server (`http://127.0.0.1:8000/`).

---

## 1. Prerequisites & Test Accounts

Ensure your local server is running:
```bash
python manage.py runserver
```

### Pre-configured Seed Accounts
| Role | Username | Password | Notes |
| :--- | :--- | :--- | :--- |
| **Customer** | `rahul` | `rahul123` | Active customer with bookings |
| **Provider** | `anand` | `anand123` | Verified plumbing & repair provider |
| **Admin** | `admin` | `admin123` | Platform owner / staff access |

---

## 2. Step-by-Step Walkthrough Flow

### Step 1: Customer Creates a Booking
1. Log in as customer `rahul`.
2. Browse Services $\rightarrow$ Select **Main Line Pipe Fitting** (₹1,000.00).
3. Choose a booking date and time slot $\rightarrow$ Click **Confirm Booking**.
4. Observe the initial booking status:
   - Status: `Pending` or `Accepted`
   - Base Service Charge: **₹1,000.00**
   - Materials: **₹0.00**
   - Total Amount: **₹1,000.00**

---

### Step 2: Provider Inspects & Proposes Materials
1. Log out and log in as provider `anand`.
2. Navigate to **Provider Portal** $\rightarrow$ **Job Requests** / **My Jobs** $\rightarrow$ Click on the new booking.
3. Accept the job if pending.
4. Locate the **Materials & Parts (Reimbursed at 100%)** section.
5. Click **+ Add Material / Part**.
6. Enter details:
   - Item Name: `Heavy Duty Brass Valve`
   - Quantity: `1`
   - Unit Price: `300.00`
   - Upload Receipt: Select any image or PDF receipt (`bill.jpg` or `bill.pdf`).
7. Click **Submit for Approval**.
8. Notice:
   - The item status is displayed as **Pending Approval**.
   - Note to provider: *"Customer must approve before checkout."*

---

### Step 3: Customer Receives Notification & Approves Costs
1. Log out and log back in as customer `rahul`.
2. Click the **Bell Icon (Notifications)** in the navbar:
   - Verify notification: *"Provider Anand Kumar added materials for Booking #... (₹300.00). Please review and approve."*
3. Open the booking details page (`/my-bookings/<id>/`).
4. Notice the high-visibility **Materials Approval Required** banner:
   - Line item: `Heavy Duty Brass Valve (x1) — ₹300.00`
   - View Receipt link (loads safely via `/materials/<id>/receipt/`).
5. Click **✓ Approve Material Costs**:
   - The status updates to **Approved**.
   - Total booking amount updates dynamically: **₹1,000.00 + ₹300.00 = ₹1,300.00**.

*(Optional test: Propose a second material item and click "Decline Additional Costs" to verify that rejected items are removed from the payable total).*

---

### Step 4: Customer Proceeds to UPI-Only Checkout
1. On the booking detail page, click **Proceed to Payment / Pay Now**.
2. Arrive at `/services/checkout/<id>/`.
3. Verify the UPI-only UI:
   - **No credit/debit card forms, CVV boxes, or netbanking dropdowns are present**.
   - **Option A (UPI QR Code)**: Dynamic QR code displaying `upi://pay?pa=servora.pay@icici&pn=Servora+Marketplace&am=1300.00&cu=INR...`.
   - **Option B (Pay with UPI ID)**: Input field for customer VPA (e.g., `rahul@oksbi`).
4. Select **Pay with UPI ID** or use the **Test Simulation Button** (`Verify & Complete UPI Payment`).
5. Click the payment confirmation button.
6. The payment order is verified, and you are redirected to the success screen:
   - Status: **Paid**
   - Amount: **₹1,300.00**

---

### Step 5: Provider Settlement & Earnings Verification
1. Log out and log in as provider `anand`.
2. Navigate to **Provider Portal** $\rightarrow$ **Settlements** (`/provider/settlements/`).
3. Inspect the Settlement Ledger row for the completed booking:
   - Service Charge: **₹1,000.00**
   - Servora Platform Fee (10% of Service only): **₹100.00**
   - Materials Reimbursement (100% reimbursed, 0% commission): **+ ₹300.00**
   - Net Take-Home Payout: **₹1,200.00** (`₹900 service + ₹300 materials`)
4. Verify that the platform fee was calculated **only on the service fee** and did not deduct 10% from the hardware parts.

---

### Step 6: Commercial Receipt & Audit Trail
1. Log out and log in as customer `rahul` (or provider `anand`).
2. Go to the booking detail page $\rightarrow$ Click **View Commercial Receipt** (`/my-bookings/<id>/receipt/`).
3. Verify the itemized receipt layout:
   - Base Service Fee: ₹1,000.00
   - Approved Materials & Parts: + ₹300.00
   - Servora Fee: ₹100.00
   - Provider Net Share: ₹1,200.00
   - Total Paid: ₹1,300.00
4. Verify the statutory notice at the bottom:
   - Confirms commercial service receipt between customer and independent contractor.
   - Disclaims government taxation and GST claims (0% GST claimed).

---

### Step 7: Platform Payment Dashboard (Admin)
1. Log out and log in as `admin`.
2. Visit Platform Payment Dashboard (`/platform/payments/`).
3. Check metrics:
   - Total Platform Commission: shows 10% fee collected on service portion.
   - Materials Disbursed: shows material reimbursements tracked.
   - Demo revenue (₹6,188) is strictly separated from live/pilot actual collections.
