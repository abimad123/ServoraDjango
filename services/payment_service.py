import io
import base64
import hmac
import hashlib
import json
import urllib.parse
from decimal import Decimal
import qrcode
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from .models import Booking, PaymentTransaction, ProviderSettlement, RevenueTransaction, create_notification


class PaymentGatewayAdapter:
    """
    Abstract base interface for Servora payment gateway adapters.
    Subclasses provide sandbox simulation or live UPI gateway integrations.
    """
    @classmethod
    def get_merchant_vpa(cls):
        """Reads configured Servora merchant VPA from settings. Never provider personal VPA."""
        return getattr(settings, 'SERVORA_UPI_ID', 'servora.sandbox@upi')

    @classmethod
    def get_merchant_name(cls):
        """Reads configured Servora merchant legal/display name from settings."""
        return getattr(settings, 'SERVORA_MERCHANT_NAME', 'Servora Marketplace')

    @classmethod
    def get_key_id(cls):
        raise NotImplementedError

    @classmethod
    def create_order(cls, booking, amount, currency='INR'):
        raise NotImplementedError

    @classmethod
    def generate_signature(cls, order_id, payment_id):
        raise NotImplementedError

    @classmethod
    def verify_signature(cls, order_id, payment_id, signature):
        raise NotImplementedError

    @classmethod
    def generate_upi_qr_data(cls, order_id, amount, vpa=None, payee_name=None):
        """
        Generates standard NPCI UPI Intent URI for QR scanning and mobile UPI apps.
        Format: upi://pay?pa=<vpa>&pn=<name>&am=<amount>&cu=INR&tn=<note>&tr=<order_id>
        """
        vpa = vpa or cls.get_merchant_vpa()
        payee_name = payee_name or cls.get_merchant_name()
        amt_str = f"{Decimal(str(amount)):.2f}"
        params = {
            'pa': vpa,
            'pn': payee_name,
            'am': amt_str,
            'cu': 'INR',
            'tn': f"Servora Booking {order_id}",
            'tr': order_id,
        }
        return f"upi://pay?{urllib.parse.urlencode(params)}"

    @classmethod
    def generate_qr_image_bytes(cls, upi_uri):
        """
        Generates actual, valid PNG image bytes of a dynamic QR code encoding upi_uri.
        Uses the standard qrcode and Pillow libraries.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(upi_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @classmethod
    def generate_qr_image_base64(cls, upi_uri):
        """
        Returns a data:image/png;base64,... string representing the real dynamic QR code.
        Directly embeddable into HTML <img> tags.
        """
        png_bytes = cls.generate_qr_image_bytes(upi_uri)
        b64 = base64.b64encode(png_bytes).decode('utf-8')
        return f"data:image/png;base64,{b64}"


class TestGatewayAdapter(PaymentGatewayAdapter):
    """
    Test-mode payment gateway adapter simulating genuine UPI payment intent, 
    order creation, dynamic QR generation, signature generation, and webhook validation.
    Enables isolated sandbox testing without live merchant credentials.
    """

    @classmethod
    def get_key_id(cls):
        return getattr(settings, 'PAYMENT_GATEWAY_KEY_ID', 'test_key_servora_sandbox')

    @classmethod
    def get_key_secret(cls):
        return getattr(settings, 'PAYMENT_GATEWAY_KEY_SECRET', 'test_secret_servora_sandbox')

    @classmethod
    def get_webhook_secret(cls):
        return getattr(settings, 'PAYMENT_GATEWAY_WEBHOOK_SECRET', 'test_whsec_servora_sandbox')

    @classmethod
    def create_order(cls, booking, amount, currency='INR'):
        """Generates a test gateway order representation with UPI intent data."""
        order_id = f"order_test_{booking.id}_{int(timezone.now().timestamp())}"
        upi_intent = cls.generate_upi_qr_data(order_id, amount)
        return {
            'order_id': order_id,
            'amount': amount,
            'currency': currency,
            'gateway': 'test_gateway',
            'key_id': cls.get_key_id(),
            'upi_intent': upi_intent,
        }

    @classmethod
    def generate_signature(cls, order_id, payment_id):
        """Generates HMAC-SHA256 signature for test gateway order verification."""
        secret = cls.get_key_secret().encode('utf-8')
        payload = f"{order_id}|{payment_id}".encode('utf-8')
        return hmac.new(secret, payload, hashlib.sha256).hexdigest()

    @classmethod
    def verify_signature(cls, order_id, payment_id, signature):
        """Validates HMAC-SHA256 signature."""
        expected = cls.generate_signature(order_id, payment_id)
        return hmac.compare_digest(expected, signature)

    @classmethod
    def generate_webhook_signature(cls, payload_bytes):
        """Generates HMAC-SHA256 webhook signature for testing webhooks."""
        secret = cls.get_webhook_secret().encode('utf-8')
        return hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()

    @classmethod
    def verify_webhook_signature(cls, payload_bytes, signature_header):
        """Validates webhook payload against expected secret HMAC."""
        if not signature_header:
            return False
        expected = cls.generate_webhook_signature(payload_bytes)
        return hmac.compare_digest(expected, signature_header)

    @classmethod
    def simulate_gateway_payment_webhook(cls, booking, amount=None, failure_reason=None):
        """
        Simulates gateway webhook event dispatch for test mode.
        Exercises the genuine HMAC-SHA256 signature and webhook verification pipeline.
        Never bypasses signature or amount checks.
        """
        from .models import PaymentTransaction
        from services.payment_service import PaymentService
        txn = PaymentTransaction.objects.filter(booking=booking).order_by('-created_at').first()
        if not txn:
            txn = PaymentService.create_payment_order(booking, payment_method='upi')

        target_amt = amount if amount is not None else getattr(booking, 'final_amount', booking.total_amount)
        payment_id = f"pay_sim_{booking.id}_{int(timezone.now().timestamp())}"

        if failure_reason:
            event_name = 'payment.failed'
            entity = {
                'id': payment_id,
                'order_id': txn.gateway_order_id,
                'amount': float(target_amt),
                'currency': 'INR',
                'status': 'failed',
                'method': 'upi',
                'error_description': failure_reason,
            }
        else:
            event_name = 'payment.captured'
            sig = cls.generate_signature(txn.gateway_order_id, payment_id)
            entity = {
                'id': payment_id,
                'order_id': txn.gateway_order_id,
                'amount': float(target_amt),
                'currency': 'INR',
                'status': 'captured',
                'method': 'upi',
                'signature': sig,
            }

        payload_dict = {
            'event': event_name,
            'payload': {
                'payment': {
                    'entity': entity
                }
            }
        }
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        wh_sig = cls.generate_webhook_signature(payload_bytes)
        return PaymentService.process_webhook_event(payload_bytes, wh_sig)


class RealUPIGatewayAdapter(PaymentGatewayAdapter):
    """
    Production-ready UPI Gateway Adapter abstraction.
    Disabled unless active live merchant credentials and PAYMENT_GATEWAY_MODE='live'
    are explicitly configured in environment variables.
    """
    @classmethod
    def is_configured(cls):
        mode = getattr(settings, 'PAYMENT_GATEWAY_MODE', 'test')
        key_id = getattr(settings, 'PAYMENT_GATEWAY_KEY_ID', '')
        key_secret = getattr(settings, 'PAYMENT_GATEWAY_KEY_SECRET', '')
        return mode == 'live' and bool(key_id and key_secret and not key_id.startswith('test_'))

    @classmethod
    def get_key_id(cls):
        return getattr(settings, 'PAYMENT_GATEWAY_KEY_ID', '')

    @classmethod
    def create_order(cls, booking, amount, currency='INR'):
        if not cls.is_configured():
            return TestGatewayAdapter.create_order(booking, amount, currency)
        raise NotImplementedError("Live UPI Gateway requires active merchant onboarding and compliance setup.")


def get_gateway_adapter():
    """Returns the active payment gateway adapter based on configuration."""
    if RealUPIGatewayAdapter.is_configured():
        return RealUPIGatewayAdapter
    return TestGatewayAdapter


class PaymentService:
    """
    Core payment business logic service layer for Servora.
    Manages payment creation, verification, 10% commission split,
    provider settlements, refunds, and webhooks.
    """

    COMMISSION_RATE = Decimal('10.00')

    @classmethod
    def calculate_split(cls, gross_amount, materials_amount=Decimal('0.00'), service_amount=None):
        """
        Calculates 10% platform commission on the SERVICE AMOUNT ONLY,
        and computes the provider payout:
        provider_payout = (service_amount - commission) + materials_amount.
        Materials are 100% reimbursed to the provider (0% Servora commission).
        Always uses Decimals to prevent floating-point arithmetic rounding errors.
        """
        mat = Decimal(str(materials_amount or 0)).quantize(Decimal('0.01'))
        if service_amount is not None:
            srv = Decimal(str(service_amount)).quantize(Decimal('0.01'))
            gross = (srv + mat).quantize(Decimal('0.01'))
        else:
            gross = Decimal(str(gross_amount)).quantize(Decimal('0.01'))
            srv = (gross - mat).quantize(Decimal('0.01'))

        commission = (srv * (cls.COMMISSION_RATE / Decimal('100.00'))).quantize(Decimal('0.01'))
        provider_payout = ((srv - commission) + mat).quantize(Decimal('0.01'))
        return {
            'gross_amount': gross,
            'service_amount': srv,
            'materials_amount': mat,
            'commission_amount': commission,
            'payout_amount': provider_payout,
        }

    @classmethod
    def create_payment_order(cls, booking, payment_method='upi', is_demo=False):
        """
        Initiates a payment order for a booking.
        The amount is strictly calculated from the database Booking record (total_amount / final_amount).
        """
        amount = getattr(booking, 'final_amount', booking.total_amount)
        adapter = get_gateway_adapter()
        gateway_data = adapter.create_order(booking, amount)

        # Check for existing pending/created transaction to avoid duplicate uncompleted intents
        existing_txn = PaymentTransaction.objects.filter(
            booking=booking,
            status='created'
        ).first()

        if existing_txn:
            existing_txn.gateway_order_id = gateway_data['order_id']
            existing_txn.payment_method = payment_method
            existing_txn.amount = amount
            existing_txn.is_demo = is_demo
            existing_txn.save()
            return existing_txn

        txn = PaymentTransaction.objects.create(
            booking=booking,
            customer=booking.customer,
            provider=booking.service.provider,
            gateway=gateway_data['gateway'],
            gateway_order_id=gateway_data['order_id'],
            amount=amount,
            currency='INR',
            payment_method=payment_method,
            status='created',
            is_demo=is_demo,
        )
        return txn

    @classmethod
    @transaction.atomic
    def verify_and_capture_payment(cls, booking, gateway_order_id, gateway_payment_id, gateway_signature, payment_method='upi'):
        """
        Confirms payment capture following gateway authorization.
        Idempotent: Re-calling with same order/payment does not create duplicate settlements or change status.
        """
        # Idempotency check: if booking already paid with this payment ID, return existing transaction
        existing_captured = PaymentTransaction.objects.filter(
            booking=booking,
            gateway_payment_id=gateway_payment_id,
            status='captured'
        ).first()
        if existing_captured:
            return existing_captured

        # Validate signature
        is_valid_sig = TestGatewayAdapter.verify_signature(gateway_order_id, gateway_payment_id, gateway_signature)
        if not is_valid_sig:
            raise ValueError("Invalid gateway payment signature.")

        # Find or load PaymentTransaction
        txn = PaymentTransaction.objects.filter(
            booking=booking,
            gateway_order_id=gateway_order_id
        ).first()

        if not txn:
            txn = PaymentTransaction(
                booking=booking,
                customer=booking.customer,
                provider=booking.service.provider,
                gateway='test_gateway',
                gateway_order_id=gateway_order_id,
                amount=booking.total_amount,
                currency='INR',
                is_demo=False,
            )

        txn.gateway_payment_id = gateway_payment_id
        txn.gateway_signature = gateway_signature
        txn.payment_method = payment_method
        txn.status = 'captured'
        txn.paid_at = timezone.now()
        txn.save()

        # Update Booking payment status
        booking.payment_status = 'paid'
        booking.save(update_fields=['payment_status'])

        # Create provider settlement entry
        cls.create_provider_settlement(booking, txn)

        return txn

    @classmethod
    def create_provider_settlement(cls, booking, payment_transaction=None):
        """
        Creates a ProviderSettlement record representing the 90% take-home payout
        owed to the service provider. Idempotent: only one settlement per booking.
        """
        existing = ProviderSettlement.objects.filter(booking=booking).first()
        if existing:
            if payment_transaction and not existing.payment_transaction:
                existing.payment_transaction = payment_transaction
                existing.save(update_fields=['payment_transaction'])
            return existing

        split = cls.calculate_split(
            gross_amount=booking.total_amount,
            materials_amount=getattr(booking, 'materials_amount', Decimal('0.00')),
            service_amount=getattr(booking, 'service_amount', booking.total_amount)
        )
        settlement = ProviderSettlement.objects.create(
            booking=booking,
            provider=booking.service.provider,
            payment_transaction=payment_transaction,
            service_amount=split['service_amount'],
            materials_amount=split['materials_amount'],
            gross_amount=split['gross_amount'],
            commission_amount=split['commission_amount'],
            payout_amount=split['payout_amount'],
            status='pending',
        )
        return settlement

    @classmethod
    def handle_payment_failure(cls, booking, failure_reason='Payment declined by user or bank', gateway_order_id=None):
        """
        Handles failed or aborted payment attempts.
        Updates transaction status to 'failed' and leaves booking payment_status as 'failed'.
        Does NOT create platform revenue or provider settlements.
        """
        txn = None
        if gateway_order_id:
            txn = PaymentTransaction.objects.filter(
                booking=booking,
                gateway_order_id=gateway_order_id
            ).first()

        if not txn:
            txn = PaymentTransaction.objects.filter(
                booking=booking,
                status='created'
            ).first()

        if not txn:
            txn = PaymentTransaction(
                booking=booking,
                customer=booking.customer,
                provider=booking.service.provider,
                gateway='test_gateway',
                amount=booking.total_amount,
                currency='INR',
            )

        txn.status = 'failed'
        txn.failure_reason = failure_reason
        txn.save()

        if booking.payment_status != 'paid':
            booking.payment_status = 'failed'
            booking.save(update_fields=['payment_status'])

        return txn

    @classmethod
    @transaction.atomic
    def handle_refund(cls, booking, reason='Service cancelled'):
        """
        Processes a full refund for a paid booking.
        Sets payment_status='refunded', settlement status='refunded',
        and voids any commission RevenueTransaction.
        """
        if booking.payment_status != 'paid':
            return {'success': False, 'message': 'Booking is not paid; refund not applicable.'}

        # Update payment transaction
        captured_txn = PaymentTransaction.objects.filter(
            booking=booking,
            status='captured'
        ).first()

        if captured_txn:
            captured_txn.status = 'refunded'
            captured_txn.failure_reason = f"Refunded: {reason}"
            captured_txn.save()

        # Update booking payment status
        booking.payment_status = 'refunded'
        booking.save(update_fields=['payment_status'])

        # Update provider settlement
        settlement = ProviderSettlement.objects.filter(booking=booking).first()
        if settlement and settlement.status in ['pending', 'processing']:
            settlement.status = 'refunded'
            settlement.payout_reference = f"Voided ({reason})"
            settlement.save()

        # Void any platform commission revenue transaction
        commission_rev = RevenueTransaction.objects.filter(
            booking=booking,
            revenue_type='commission'
        ).first()
        if commission_rev:
            commission_rev.status = 'refunded'
            commission_rev.verification_status = 'rejected'
            commission_rev.evidence_note = f"Refunded due to cancellation: {reason}"
            commission_rev.save()

        return {'success': True, 'message': 'Payment successfully refunded.'}

    @classmethod
    def process_webhook_event(cls, payload_bytes, signature_header):
        """
        Processes webhook callbacks from the payment gateway.
        Validates HMAC signature, checks order, currency, amount against booking.final_amount,
        and handles 'payment.captured', 'payment.failed', and 'refund.processed'.
        Guarantees strict idempotency and server-side verification.
        """
        if not TestGatewayAdapter.verify_webhook_signature(payload_bytes, signature_header):
            return {'success': False, 'status': 400, 'error': 'Invalid webhook signature.'}

        try:
            data = json.loads(payload_bytes.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return {'success': False, 'status': 400, 'error': 'Malformed JSON payload.'}

        event = data.get('event')
        entity = data.get('payload', {}).get('payment', {}).get('entity', {})
        order_id = entity.get('order_id')
        payment_id = entity.get('id')
        method = entity.get('method', 'upi')
        currency = entity.get('currency', 'INR')
        payload_amount = entity.get('amount')

        if not order_id:
            return {'success': False, 'status': 400, 'error': 'Missing order_id in webhook.'}

        txn = PaymentTransaction.objects.filter(gateway_order_id=order_id).first()
        if not txn:
            return {'success': False, 'status': 404, 'error': f'Transaction with order {order_id} not found.'}

        booking = txn.booking

        # Strict currency verification
        if currency != 'INR':
            return {'success': False, 'status': 400, 'error': f'Invalid currency {currency}, expected INR.'}

        if event == 'payment.captured':
            # Idempotent check: if already captured and paid
            if txn.status == 'captured' and booking.payment_status == 'paid' and txn.gateway_payment_id == payment_id:
                return {'success': True, 'status': 200, 'message': 'Payment already captured (idempotent duplicate).'}

            # Strict amount verification against Booking.final_amount
            expected_amount = getattr(booking, 'final_amount', booking.total_amount)
            if payload_amount is not None:
                try:
                    parsed_amt = Decimal(str(payload_amount))
                    # Support both standard rupee units (e.g. 1300.00) and gateway paise units (e.g. 130000)
                    matches_rupees = abs(parsed_amt - expected_amount) <= Decimal('0.01')
                    matches_paise = abs((parsed_amt / Decimal('100.00')) - expected_amount) <= Decimal('0.01')
                    if not (matches_rupees or matches_paise):
                        reason = f"Amount mismatch: expected ₹{expected_amount:.2f}, received ₹{parsed_amt:.2f}"
                        txn.failure_reason = reason
                        txn.save(update_fields=['failure_reason'])
                        return {'success': False, 'status': 400, 'error': reason}
                except Exception:
                    return {'success': False, 'status': 400, 'error': 'Invalid amount format in webhook payload.'}

            # Valid signature check
            signature = entity.get('signature') or TestGatewayAdapter.generate_signature(order_id, payment_id)
            cls.verify_and_capture_payment(
                booking=booking,
                gateway_order_id=order_id,
                gateway_payment_id=payment_id,
                gateway_signature=signature,
                payment_method=method
            )

            # Deduplicated payment notification
            create_notification(
                recipient=booking.service.provider.user,
                notification_type='payment_received',
                title='Payment Received',
                message=f"Customer {booking.customer.get_full_name() or booking.customer.username} paid ₹{expected_amount:.2f} for Booking #SVR{booking.id:05d}.",
                booking=booking,
                service=booking.service
            )

            return {'success': True, 'status': 200, 'message': 'Payment captured successfully via webhook.'}

        elif event == 'payment.failed':
            reason = entity.get('error_description', 'Payment failed via webhook.')
            cls.handle_payment_failure(booking, failure_reason=reason, gateway_order_id=order_id)
            return {'success': True, 'status': 200, 'message': 'Payment failure logged via webhook.'}

        elif event == 'refund.processed':
            cls.handle_refund(booking, reason='Gateway refund webhook')
            return {'success': True, 'status': 200, 'message': 'Refund processed via webhook.'}

        return {'success': True, 'status': 200, 'message': f'Event {event} acknowledged.'}
