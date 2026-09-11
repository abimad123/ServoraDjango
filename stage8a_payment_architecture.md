# Stage 8A: Payment System, Checkout, Commission & Provider Settlement Architecture

## 1. Architectural Overview & Separation of Concerns

Servora's financial architecture is founded upon strict mathematical and structural isolation across four distinct layers:

```
[ Customer Checkout / Payment ]
             ↓
     PaymentTransaction (Gross: ₹2,000 captured)
             ├── 10% Platform Fee → RevenueTransaction (Platform Revenue: ₹200)
             └── 90% Provider Share → ProviderSettlement (Disbursement: ₹1,800)
                                            ↓
                                 [ RGM Verifiable Revenue ]
                                  (Requires external proof & audit)
```

$$\text{CUSTOMER PAYMENT} \neq \text{SERVORA REVENUE} \neq \text{PROVIDER PAYOUT} \neq \text{RGM VERIFIED REVENUE}$$

- **Gross Booking Value (GBV)**: Total customer spend for home services (e.g., ₹2,000).
- **Servora Platform Revenue**: 10% platform facilitation commission (e.g., ₹200).
- **Provider Earnings / Settlement**: 90% net take-home disbursement to local professionals (e.g., ₹1,800).
- **RGM Verified Revenue**: Audited university revenue submission strictly requiring genuine banking UTR evidence.

---

## 2. Customer Checkout Flow

1. **Service Selection & Appointment Scheduling**: Customer chooses service, date, time slot, and address.
2. **Booking Initial State**: Booking created with `status='pending'` and `payment_status='unpaid'`.
3. **Checkout Initiation**: Customer proceeds to `/checkout/<booking_id>/`.
   - Server-side amount validation strictly loads `booking.total_amount`.
   - Browser client cannot tamper with or modify service pricing or commission splits.
4. **Payment Gateway Order Creation**:
   - `PaymentService.create_payment_order()` provisions a deterministic test gateway order.
   - Generates `PaymentTransaction` in `created` status.
5. **Gateway Authorization & Digital Signature**:
   - Test gateway adapter simulates payment authorization (UPI, Card, Net Banking).
   - Generates cryptographic HMAC-SHA256 signature binding order ID and payment ID.
6. **Capture & Confirmation**:
   - Endpoint `/payments/success/<booking_id>/` validates HMAC signature.
   - Updates `PaymentTransaction.status = 'captured'` and records `paid_at`.
   - Updates `booking.payment_status = 'paid'`.
   - Instantiates `ProviderSettlement` with `status='pending'` for provider payout tracking.

---

## 3. Data Models Architecture

### A. `PaymentTransaction` (Gateway Payment Ledger)
Represents digital money movement and gateway authorization status:
- `booking`: `ForeignKey(Booking, related_name='payment_transactions')`
- `customer`: `ForeignKey(User, related_name='customer_payments')`
- `provider`: `ForeignKey(UserProfile, related_name='provider_payments')`
- `gateway`: `CharField` (`'test_gateway'`)
- `gateway_order_id`: `CharField(max_length=100, db_index=True)`
- `gateway_payment_id`: `CharField(max_length=100, db_index=True)`
- `gateway_signature`: `CharField(max_length=255)`
- `amount`: `DecimalField(max_digits=10, decimal_places=2)`
- `currency`: `CharField(max_length=10, default='INR')`
- `payment_method`: `upi`, `card`, `netbanking`, `wallet`
- `status`: `created`, `pending`, `authorized`, `captured`, `failed`, `cancelled`, `refunded`
- `failure_reason`: `TextField`
- `paid_at`: `DateTimeField`

### B. `RevenueTransaction` (Platform Revenue Ledger)
Authoritative platform earnings ledger:
- Represents earned platform commission (10%) upon service completion, Pro subscriptions (₹399/mo), and featured service listings (₹99).
- Completely isolated from gross customer payment amounts.
- Houses Stage 7.5 RGM audit attributes (`is_demo`, `verification_status`, `has_evidence`, `transaction_reference`).

### C. `ProviderSettlement` (Provider Disbursement Ledger)
Tracks the 90% payout owed to independent service professionals:
- `booking`: `ForeignKey(Booking, related_name='settlements')`
- `provider`: `ForeignKey(UserProfile, related_name='settlements')`
- `payment_transaction`: `ForeignKey(PaymentTransaction, null=True, blank=True)`
- `gross_amount`: `DecimalField` (e.g. ₹2,000.00)
- `commission_amount`: `DecimalField` (e.g. ₹200.00)
- `payout_amount`: `DecimalField` (e.g. ₹1,800.00)
- `status`: `pending`, `processing`, `paid`, `failed`, `refunded`
- `payout_reference`: Gateway transfer UTR or batch reference
- `settlement_date`: Disbursement timestamp

---

## 4. Commission & Provider Payout Calculations

All monetary calculations use Python `Decimal` with two decimal places (`quantize(Decimal('0.01'))`):

```python
COMMISSION_RATE = Decimal('10.00')

gross = Decimal(str(gross_amount)).quantize(Decimal('0.01'))
commission = (gross * (COMMISSION_RATE / Decimal('100.00'))).quantize(Decimal('0.01'))
provider_payout = (gross - commission).quantize(Decimal('0.01'))
```

Example Breakdown:
- **Service Price**: ₹2,000.00
- **Customer Pays**: ₹2,000.00 *(no surcharges)*
- **Servora Platform Commission (10%)**: ₹200.00
- **Provider Take-Home Payout (90%)**: ₹1,800.00

---

## 5. Provider Payout & UPI Settings

Service providers configure their disbursement preferences under `/provider/payout-settings/`:
- `payout_upi_id`: Virtual Payment Address (e.g., `provider@okhdfcbank`)
- `payout_upi_name`: Legal beneficiary name matching banking records
- `payout_preference`: `upi` (UPI / VPA) or `bank` (Direct IMPS / NEFT)
- `payout_status`: `not_configured`, `configured`, `verification_required`, `ready`

### Security Safeguard
Provider UPI IDs are strictly private and never displayed on public profile pages or exposed to customers. Payout interfaces feature prominent security alerts warning professionals never to disclose PINs, OTPs, or passwords.

---

## 6. Test-Mode Gateway Adapter (`TestGatewayAdapter`)

To facilitate academic evaluation and local automated test suites without live API credentials:
- Deterministic order provisioning (`order_test_<booking_id>_<timestamp>`).
- Cryptographic HMAC-SHA256 signature generation and validation:
  $$\text{Signature} = \text{HMAC-SHA256}(\text{key\_secret}, \text{order\_id} \parallel \text{"|"} \parallel \text{payment\_id})$$
- Configurable environment settings with fallback defaults:
  - `PAYMENT_GATEWAY_KEY_ID`
  - `PAYMENT_GATEWAY_KEY_SECRET`
  - `PAYMENT_GATEWAY_WEBHOOK_SECRET`

---

## 7. Webhook Architecture

Endpoint: `/payments/webhook/` (CSRF exempt)
- Validates HMAC-SHA256 signature against `PAYMENT_GATEWAY_WEBHOOK_SECRET`.
- Processes event types:
  - `payment.captured`: Idempotently verifies and captures payment, updates booking status to `paid`, and provisions settlement.
  - `payment.failed`: Records failure reason and updates booking payment status to `failed`.
  - `refund.processed`: Invokes refund protocol.
- Strict idempotency prevents duplicate disbursements or repeated revenue recording.

---

## 8. Refund Protocol

When a paid booking is cancelled or refunded via `PaymentService.handle_refund()`:
1. `PaymentTransaction.status` set to `'refunded'`.
2. `booking.payment_status` set to `'refunded'`.
3. `ProviderSettlement.status` transitioned from `'pending'` to `'refunded'`.
4. Any commission `RevenueTransaction` is voided (`status='refunded'`, `verification_status='rejected'`).

---

## 9. Regulatory Compliance & Commercial Receipts

Receipt endpoint: `/my-bookings/<booking_id>/receipt/`
- Rendered as **SERVORA COMMERCIAL SERVICE RECEIPT**.
- Displays payment capture details (Gateway reference ID, payment method, timestamp).
- Displays gross service amount, 10% platform fee, and 90% provider disbursement.
- **Zero Fake Invoices / Zero Fake GSTINs**: Contains explicit statutory disclosure confirming non-tax registration exemption under Section 22 of the CGST Act (turnover below ₹20 Lakhs).

---

## 10. Production Deployment & Live Gateway Requirements

> [!WARNING]
> **Production Warning & Merchant Onboarding Requirements**:
> The local test-mode gateway adapter is designed exclusively for development, academic evaluation, and sandbox verification. Prior to operating live real-money transactions, the platform must complete:
> 1. Formal corporate / merchant account onboarding with an RBI-authorized payment aggregator (Razorpay, Cashfree, PayU).
> 2. Provider KYC verification for automated marketplace split settlements (e.g., Razorpay Route or Cashfree Marketplace).
> 3. Statutory business registration, GST review upon exceeding turnover thresholds, and merchant terms of service compliance.
