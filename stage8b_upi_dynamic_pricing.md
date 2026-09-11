# Servora — Stage 8B: UPI-Only Payment & Dynamic Job Pricing Architecture

## 1. Overview & Objectives
Stage 8B upgrades the Servora marketplace payment subsystem to a **production-ready UPI-only architecture** combined with **dynamic job pricing & materials approval**.

In home services (such as plumbing, electrical, carpentry, and appliance repair), the initial booking price often covers labor and standard diagnostic work, while unforeseen replacement parts and hardware materials are identified on-site.

Stage 8B addresses this with:
1. **Dynamic Final Price Workflow**: Propose materials on-site $\rightarrow$ Customer approval/rejection $\rightarrow$ Price lock.
2. **0% Material Commission**: Platform commission (10%) applies strictly to the service fee. Physical material costs are 100% reimbursed to the service provider.
3. **UPI-Only Customer Checkout**: Streamlined checkout removing legacy cards, netbanking, and wallets in favor of UPI ID / VPA and standard NPCI UPI QR code scan.
4. **Pluggable Payment Gateway Architecture**: Factory-backed adapter pattern supporting local test simulations and live gateway integrations via environment variables without hardcoded or fake credentials.

---

## 2. Dynamic Pricing & Materials Approval Workflow

```
+-----------------------------------------------------------------------------------+
| 1. BOOKING CREATION                                                              |
| Customer books service (e.g., Pipe Repair).                                      |
| booking.service_amount = ₹1,000.00                                               |
| booking.materials_amount = ₹0.00                                                 |
| booking.final_amount = ₹1,000.00                                                 |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 2. ON-SITE INSPECTION & MATERIAL PROPOSAL                                         |
| Provider inspects site, buys replacement valve/pipe, and adds item:              |
|   - Name, Quantity, Unit Price, Total Price                                      |
|   - Uploads store bill / receipt image or PDF                                    |
|   - Material Status = 'pending'                                                  |
| Customer receives instant in-app notification ('materials_added').               |
| Pending materials do NOT yet affect booking.final_amount.                        |
+-----------------------------------------------------------------------------------+
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                         ▼
+---------------------------------------+ +---------------------------------------+
| 3A. CUSTOMER REJECTS PROPOSAL        | | 3B. CUSTOMER APPROVES PROPOSAL        |
| - Material status -> 'rejected'       | | - Material status -> 'approved'       |
| - Notification sent to provider       | | - booking.materials_amount updated    |
| - final_amount remains base service   | | - booking.final_amount recalculated   |
| - Customer pays only base fee         | | - Items locked from provider edits    |
+---------------------------------------+ +---------------------------------------+
                                                              │
                                                              ▼
+-----------------------------------------------------------------------------------+
| 4. LOCKED FINAL AMOUNT & CHECKOUT                                                 |
| Example: Base ₹1,000 + Approved Materials ₹300 = Total ₹1,300.00                 |
| Payment Order generated for ₹1,300 via UPI QR or UPI Intent / VPA.                |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
| 5. SETTLEMENT & REVENUE SPLIT                                                     |
| - Servora 10% Platform Fee: ₹1,000 * 10% = ₹100.00                               |
| - Provider Service Earning: ₹1,000 * 90% = ₹900.00                               |
| - Provider Material Reimbursement: 100% of ₹300 = ₹300.00                        |
| - Net Provider Payout: ₹900 + ₹300 = ₹1,200.00                                    |
+-----------------------------------------------------------------------------------+
```

---

## 3. Financial Split & Commission Mathematics

To maintain fair marketplace incentives, platform commission is never levied on physical hardware parts:

$$\text{Final Amount} = \text{Service Amount} + \text{Approved Materials Amount}$$

$$\text{Platform Commission} = \text{Service Amount} \times 10\%$$

$$\text{Provider Net Payout} = (\text{Service Amount} \times 90\%) + \text{Approved Materials Amount}$$

### Example Reconciliation
| Component | Amount | Commission Rate | Servora Retained | Provider Allocated |
| :--- | :--- | :--- | :--- | :--- |
| Labor / Service Fee | ₹1,000.00 | 10.00% | ₹100.00 | ₹900.00 |
| Approved Parts & Materials | ₹300.00 | 0.00% | ₹0.00 | ₹300.00 |
| **Gross Total** | **₹1,300.00** | — | **₹100.00** | **₹1,200.00** |

---

## 4. NPCI UPI Standard QR & Intent Specification

Servora generates standard NPCI-compliant deep links and QR codes:

```
upi://pay?pa=servora.pay@icici&pn=Servora+Marketplace&am=1300.00&cu=INR&tn=Booking+SVR00001&tr=SVR-ORD-1-78A9B2
```

### Parameter Breakdown:
- `pa`: Payee VPA (Virtual Payment Address).
- `pn`: Payee Legal / Display Name (`Servora Marketplace`).
- `am`: Transaction amount formatted to 2 decimal places.
- `cu`: Currency code (`INR`).
- `tn`: Transaction note containing booking identifier.
- `tr`: Unique reference ID (Order ID / Gateway tracking reference).

The frontend dynamically encodes this payload into a QR code rendered using QR SVG generators or client-side SVG elements, enabling scanning with Google Pay, PhonePe, Paytm, BHIM, or any UPI 2.0 app.

---

## 5. Gateway Architecture & Adapter Pattern

The gateway system follows the open-closed principle via `PaymentGatewayAdapter` in `services/payment_service.py`:

```
                 +───────────────────────────+
                 |   PaymentGatewayAdapter   |
                 +───────────────────────────+
                 | + create_order()          |
                 | + verify_payment()        |
                 | + initiate_refund()       |
                 | + generate_upi_qr()       |
                 +───────────────────────────+
                               ▲
                               │
             ┌─────────────────┴─────────────────┐
             │                                   │
+─────────────────────────+         +─────────────────────────+
|    TestGatewayAdapter   |         |   RealUPIGatewayAdapter |
+─────────────────────────+         +─────────────────────────+
| - NPCI QR link builder  |         | - Razorpay / Cashfree   |
| - Instant test sandbox  |         | - Webhook verification  |
| - Deterministic orders  |         | - Live UPI intent rails |
+─────────────────────────+         +─────────────────────────+
```

### Factory Initialization
`get_gateway_adapter()` reads `settings.PAYMENT_GATEWAY_PROVIDER`:
- If set to `'test'` (default): Returns `TestGatewayAdapter`.
- If set to `'razorpay'`, `'cashfree'`, or `'upi_live'`: Returns `RealUPIGatewayAdapter` configured with `settings.RAZORPAY_KEY_ID` and `settings.RAZORPAY_KEY_SECRET`.

---

## 6. Access Control & Security Invariants

1. **Receipt File Protection (`secure_material_receipt_view`)**:
   - Store bills and receipts uploaded under `materials/receipts/` are guarded through a view-layer permission check.
   - Only the assigned provider, the booking's customer, or platform staff can access or download receipt files (HTTP 403 for unauthorized users).
2. **Immutability of Approved Materials**:
   - Once a material item is in status `'approved'`, the provider cannot edit or delete it.
   - Once a booking is `'completed'` or `'paid'`, no further materials can be added.
3. **No Sensitive Banking Data**:
   - The platform never solicits, receives, or persists debit/credit card numbers, CVVs, netbanking passwords, or UPI PINs.
4. **Statutory Commercial Receipts**:
   - Generated receipts are commercial invoices between independent service providers and customers.
   - Explicitly disclaim government tax collection (0% GST claimed) to prevent fraudulent compliance assertions.
