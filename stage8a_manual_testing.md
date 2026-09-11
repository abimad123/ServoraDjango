# Stage 8A: Manual Testing & Verification Guide

This guide provides step-by-step manual walkthrough scenarios for testing customer checkout, simulated payment gateway flows, provider payout configuration, provider settlements, and administrative audit dashboards.

---

## Prerequisites
- Start Django development server: `python manage.py runserver`
- Open web browser at: `http://127.0.0.1:8000/`

---

## Scenario 1: Successful Customer Checkout (UPI Simulation)

1. **Log in as Customer**:
   - Credentials: `arun_menon` / `password123` (or any customer account).
2. **Schedule a Service**:
   - Navigate to `/services/` and select **Ceiling Fan Repair** or any active service.
   - Click **Book Now**, choose tomorrow's date, 10:00 AM slot, enter address, and submit.
   - You will land on Booking Details (`/my-bookings/<id>/`).
3. **Initiate Checkout**:
   - Notice the status: **Pending Approval** and **Unpaid**.
   - Click the prominent **💳 Pay Now** button.
   - You are navigated to `/checkout/<id>/`.
4. **Inspect Transparent Breakdown**:
   - Verify Service Price equals Total to Pay (e.g., ₹850).
   - Verify 10% Servora Commission (₹85) and 90% Provider Share (₹765) are displayed as included.
5. **Simulate Payment Capture**:
   - Keep payment method selected as **UPI / QR Transfer**.
   - Click **💳 Pay ₹... (Confirm Capture)**.
6. **Verify Result**:
   - Redirects to Booking Details with green notification: `Payment of ₹... confirmed successfully!`.
   - Payment status badge updates to **✓ Paid**.
   - Provider receives a database notification: `Payment Received`.

---

## Scenario 2: Simulated Payment Failure & Retry Flow

1. **Open an Unpaid Booking**:
   - Go to `/my-bookings/` and click **💳 Pay** on an unpaid booking.
2. **Simulate Failure**:
   - On `/checkout/<id>/`, click **Simulate Payment Failure / Cancel**.
3. **Verify Result**:
   - Redirects back to checkout with warning: `Payment was not completed: Simulated customer cancellation in test mode. You can retry anytime.`.
   - Booking payment status remains `failed` / `unpaid`.
   - Zero revenue or settlements are created.
4. **Retry Payment**:
   - Click **Pay (Confirm Capture)** to confirm the customer can successfully complete payment upon retry.

---

## Scenario 3: Customer Payment History

1. **Navigate to Payment History**:
   - In the top navigation or footer, click **Payment History** (or visit `/payments/history/`).
2. **Verify Ledger**:
   - The captured payment appears with reference ID (e.g., `pay_test_...`), amount, payment method, and `✓ Paid` badge.
   - Total Settled Spend metric card accurately sums captured transactions.

---

## Scenario 4: Provider Payout & UPI Settings

1. **Log in as Service Provider**:
   - Credentials: `plumber_john` / `password123`.
2. **Navigate to Payout Settings**:
   - Click **Payout Settings** in the provider sidebar (or visit `/provider/payout-settings/`).
3. **Inspect Security Warning**:
   - Confirm prominent red warning: `Never enter your UPI PIN, OTP, ATM PIN, or Internet Banking password`.
4. **Configure Handle**:
   - Enter UPI ID: `john.plumber@okaxis`
   - Enter Beneficiary Name: `John Mathew`
   - Select Preferred Channel: `UPI / VPA Electronic Settlement`
   - Click **Save Payout Settings**.
5. **Verify Confirmation**:
   - Status updates to **Ready for Payout Disbursements**.

---

## Scenario 5: Provider Settlement Ledger

1. **Navigate to Settlements**:
   - In the provider sidebar, click **Settlements** (or visit `/provider/settlements/`).
2. **Verify Financial Ledger**:
   - 4 summary cards: **Pending Settlement**, **Disbursed Payouts**, **Gross Volume**, and **Servora Fee (10%)**.
   - Table displays each customer booking, gross customer payment, 10% platform fee deduction, and 90% net payout.
   - Confirm only John Mathew's settlements are visible.

---

## Scenario 6: Cancellation & Refund Flow

1. **Log in as Customer**:
   - Open a booking that was marked **✓ Paid** but remains in **Pending Approval** state.
2. **Cancel Booking**:
   - Click **Cancel Booking** and confirm browser prompt.
3. **Verify Refund Handling**:
   - Booking status becomes `Cancelled`, payment status becomes `Refunded`.
   - In database / admin, associated `ProviderSettlement` is transitioned to `Refunded / Cancelled`.
   - Customer's payment history marks transaction as `Refunded`.

---

## Scenario 7: Platform Payment Administration

1. **Log in as Staff Administrator**:
   - Visit `/platform/payments/`.
2. **Verify Executive Metrics**:
   - Total Gross Booking Value (GBV)
   - Platform Commission (10%)
   - Provider Share (90%)
   - Status counters: Captured, Failed, Pending, Refunded.
   - Gateway transactions ledger and provider disbursement table.
3. **Security Test**:
   - Log in as customer or provider and attempt accessing `/platform/payments/`. Confirm 302 redirect / access restriction.
