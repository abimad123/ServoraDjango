from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from users.models import UserProfile
from decimal import Decimal
from datetime import date


class Category(models.Model):
    """
    Service category (e.g. Plumbing, Electrical, Cleaning, Painting).
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon_name = models.CharField(
        max_length=50, 
        default='wrench',
        help_text="Icon identifier (e.g. spark, wrench, zap, paint, hammer, leaf)"
    )
    description = models.TextField(blank=True, default='')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Service(models.Model):
    """
    Individual home service offered by a verified provider.
    """
    provider = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='services')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='services')
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Starting price in INR (₹)")
    duration_estimate = models.CharField(max_length=100, default='1-2 hours')
    location = models.CharField(max_length=120, default='Kannur')
    image = models.ImageField(upload_to='services/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            while Service.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - ₹{self.price} ({self.provider.user.username})"

    @property
    def average_rating(self):
        reviews = self.reviews.all()
        if reviews.exists():
            return round(sum(r.rating for r in reviews) / reviews.count(), 1)
        return 5.0

    @property
    def reviews_count(self):
        return self.reviews.count()

    @property
    def has_active_featured_listing(self):
        return self.featured_promotions.filter(is_active=True, end_date__gte=date.today()).exists()


class Booking(models.Model):
    """
    Booking placed by a customer for a specific provider service.
    Calculates and tracks the platform's commission fee.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('accepted', 'Accepted / In Progress'),
        ('completed', 'Completed'),
        ('declined', 'Declined'),
        ('cancelled', 'Cancelled'),
    )
    PAYMENT_STATUS_CHOICES = (
        ('unpaid', 'Unpaid'),
        ('pending', 'Payment Pending'),
        ('paid', 'Paid'),
        ('failed', 'Payment Failed'),
        ('refunded', 'Refunded'),
    )

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='bookings')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateField()
    booking_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(
        max_length=20, 
        choices=PAYMENT_STATUS_CHOICES, 
        default='unpaid',
        help_text="Financial settlement status of the customer booking."
    )
    service_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Base price for the agreed service."
    )
    materials_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Total approved physical materials and parts reimbursement."
    )
    final_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=Decimal('0.00'),
        help_text="Final payable total locked after materials approval (service + materials)."
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_rate = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=10.00, 
        help_text="Platform commission percentage (default 10%)"
    )
    commission_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text="Calculated platform revenue earned on completion (10% of service charge)"
    )
    address = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Automatically initialize service_amount if empty
        if (not self.service_amount or self.service_amount == Decimal('0.00')) and self.total_amount:
            self.service_amount = Decimal(str(self.total_amount))
        elif (not self.service_amount or self.service_amount == Decimal('0.00')) and hasattr(self, 'service') and self.service:
            self.service_amount = Decimal(str(self.service.price))

        if not self.materials_amount:
            self.materials_amount = Decimal('0.00')

        # Commission applies strictly to the service amount (0% commission on materials!)
        if self.service_amount:
            self.commission_amount = (Decimal(str(self.service_amount)) * (Decimal(str(self.commission_rate)) / Decimal(100))).quantize(Decimal('0.01'))

        # Final amount is the sum of base service and approved materials
        if self.service_amount is not None:
            self.final_amount = (Decimal(str(self.service_amount)) + Decimal(str(self.materials_amount))).quantize(Decimal('0.01'))
            self.total_amount = self.final_amount

        super().save(*args, **kwargs)

    @property
    def provider_earning(self):
        """
        Returns the net take-home earnings for the provider:
        (service_amount - commission_amount) + 100% of materials_amount.
        """
        srv = self.service_amount if (self.service_amount and self.service_amount > 0) else (self.total_amount or Decimal('0.00'))
        comm = self.commission_amount or Decimal('0.00')
        mat = self.materials_amount or Decimal('0.00')
        return (Decimal(str(srv)) - Decimal(str(comm))) + Decimal(str(mat))

    @property
    def has_pending_materials(self):
        return self.materials.filter(status='pending').exists()

    @property
    def pending_materials_total(self):
        return self.materials.filter(status='pending').aggregate(total=models.Sum('total_price'))['total'] or Decimal('0.00')

    @property
    def approved_materials_total(self):
        return self.materials.filter(status='approved').aggregate(total=models.Sum('total_price'))['total'] or Decimal('0.00')

    def __str__(self):
        return f"Booking #{self.id}: {self.service.title} by {self.customer.username} ({self.get_status_display()})"


class BookingMaterial(models.Model):
    """
    Dynamic on-the-job material or replacement part added by service provider.
    Requires explicit customer review and approval before becoming payable.
    Materials are 100% reimbursed to provider (0% Servora platform commission).
    """
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='materials')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    receipt_image = models.FileField(upload_to='material_receipts/', blank=True, null=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='added_materials')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def save(self, *args, **kwargs):
        # Strictly calculate total_price server-side
        self.total_price = (Decimal(str(self.quantity)) * Decimal(str(self.unit_price))).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} (x{self.quantity}) - ₹{self.total_price} [{self.get_status_display()}] for Booking #{self.booking.id}"




class Review(models.Model):
    """
    Customer review and star rating for a service/provider.
    """
    RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_reviews')
    booking = models.OneToOneField(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='review')
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES, default=5)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.rating}★ Review by {self.customer.username} on {self.service.title}"


class FeaturedListing(models.Model):
    """
    Tracks paid promotions where a provider pays to feature a service.
    """
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='featured_promotions')
    fee_paid = models.DecimalField(max_digits=8, decimal_places=2, default=99.00)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Featured: {self.service.title} (₹{self.fee_paid})"

    @property
    def is_currently_active(self):
        return self.is_active and self.end_date >= date.today()


class RevenueTransaction(models.Model):
    """
    Centralized financial ledger recording all realized platform revenue.
    Captures:
    1. 10% Booking Commissions from completed jobs
    2. Provider Pro Subscriptions (₹399/mo)
    3. Featured Service Listings (₹99 for 3 days)
    """
    REVENUE_TYPES = (
        ('commission', 'Booking Commission'),
        ('subscription', 'Pro Subscription'),
        ('featured', 'Featured Service Listing'),
    )
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    )
    VERIFICATION_STATUS_CHOICES = (
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )
    PAYMENT_METHOD_CHOICES = (
        ('upi', 'UPI / QR Transfer'),
        ('bank_transfer', 'Bank IMPS/NEFT'),
        ('card', 'Debit / Credit Card'),
        ('other', 'Other Digital Payment'),
        ('cash', 'Cash (Ineligible for RGM)'),
    )

    revenue_type = models.CharField(max_length=20, choices=REVENUE_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='revenue_transactions')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='revenue_transactions')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='revenue_transactions')
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')

    # Stage 7.5: Verifiable Pilot & Audit Fields
    is_demo = models.BooleanField(
        default=False,
        help_text="True if synthetic demonstration/seed transaction; False if genuine pilot record."
    )
    verification_status = models.CharField(
        max_length=20,
        choices=VERIFICATION_STATUS_CHOICES,
        default='pending',
        help_text="Administrative audit verification state."
    )
    transaction_reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Bank/UPI UTR or transfer reference number."
    )
    payment_method = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        choices=PAYMENT_METHOD_CHOICES,
        help_text="Actual electronic payment method used."
    )
    payment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date genuine payment was credited in bank/account."
    )
    has_evidence = models.BooleanField(
        default=False,
        help_text="True if external proof (bank statement, customer receipt) has been inspected."
    )
    evidence_note = models.TextField(
        blank=True,
        help_text="Auditor notes regarding banking reference, invoice, or screenshot verification."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['revenue_type', 'booking'],
                condition=models.Q(revenue_type='commission', booking__isnull=False),
                name='unique_commission_per_booking'
            )
        ]

    @property
    def is_rgm_verified(self):
        """
        Returns True only if the transaction satisfies all SCRGM verifiable revenue standards:
        1. Not synthetic/seeded demonstration data (is_demo == False)
        2. Transaction settled (status == 'completed')
        3. Formally audited by staff (verification_status == 'verified')
        4. External banking/receipt audit proof confirmed (has_evidence == True)
        5. Valid non-empty transaction reference / UTR recorded
        """
        return (
            not self.is_demo
            and self.status == 'completed'
            and self.verification_status == 'verified'
            and self.has_evidence
            and bool(self.transaction_reference and self.transaction_reference.strip())
        )

    def __str__(self):
        demo_tag = " [DEMO]" if self.is_demo else ""
        verif_tag = f" ({self.get_verification_status_display()})" if not self.is_demo else ""
        return f"[{self.get_revenue_type_display()}]{demo_tag} ₹{self.amount} - {self.provider.user.username}{verif_tag}"


class PaymentTransaction(models.Model):
    """
    Represents customer payment gateway transactions for bookings.
    Maintains payment lifecycle independent of platform revenue or provider payouts.
    """
    STATUS_CHOICES = (
        ('created', 'Created'),
        ('pending', 'Pending'),
        ('authorized', 'Authorized'),
        ('captured', 'Captured / Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded'),
    )
    PAYMENT_METHOD_CHOICES = (
        ('upi', 'UPI / QR Transfer'),
        ('card', 'Debit / Credit Card'),
        ('netbanking', 'Net Banking'),
        ('wallet', 'Digital Wallet'),
        ('other', 'Other'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payment_transactions')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_payments')
    provider = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='provider_payments')
    gateway = models.CharField(max_length=50, default='test_gateway')
    gateway_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True, db_index=True)
    gateway_signature = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default='upi')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='created')
    failure_reason = models.TextField(blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    is_demo = models.BooleanField(default=False, help_text="True if synthetic test-mode transaction.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Payment #{self.id} (₹{self.amount}) - {self.get_status_display()} [{self.gateway_payment_id or self.gateway_order_id or 'Pending'}]"


class ProviderSettlement(models.Model):
    """
    Represents settlement and disbursement of provider earnings (90% of Gross Booking Value)
    after deducting the 10% Servora platform commission.
    """
    STATUS_CHOICES = (
        ('pending', 'Pending Settlement'),
        ('processing', 'Processing Disbursement'),
        ('paid', 'Settled / Paid'),
        ('failed', 'Settlement Failed'),
        ('refunded', 'Refunded / Cancelled'),
    )

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='settlements')
    provider = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='settlements')
    payment_transaction = models.ForeignKey(
        PaymentTransaction, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='settlements'
    )
    service_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    materials_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    payout_reference = models.CharField(max_length=100, blank=True, default='')
    settlement_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Settlement #{self.id} for Booking #{self.booking.id} - ₹{self.payout_amount} to {self.provider.user.username} ({self.get_status_display()})"



class Notification(models.Model):
    """
    Database-backed notifications for customers and service providers.
    Supports booking lifecycle events, reviews, subscriptions, and featured promotions.
    """
    NOTIFICATION_TYPES = (
        ('booking_created', 'New Booking Request'),
        ('booking_accepted', 'Booking Accepted'),
        ('booking_declined', 'Booking Declined'),
        ('booking_cancelled', 'Booking Cancelled'),
        ('booking_completed', 'Service Completed'),
        ('review_received', 'New Review Received'),
        ('subscription_activated', 'Pro Subscription Activated'),
        ('featured_listing_activated', 'Service Featured'),
        ('materials_added', 'Materials Proposal Added'),
        ('materials_approved', 'Materials Approved'),
        ('materials_rejected', 'Materials Rejected'),
        ('payment_received', 'Payment Confirmed'),
        ('refund_processed', 'Payment Refunded'),
    )

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=35, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name='notifications')
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL, related_name='notifications')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.title} ({'Read' if self.is_read else 'Unread'})"


def create_notification(recipient, notification_type, title, message, booking=None, service=None):
    """
    Creates a database-backed notification for a user with duplicate prevention for critical state transitions.
    """
    if booking and notification_type in ['booking_created', 'booking_accepted', 'booking_declined', 'booking_cancelled', 'booking_completed']:
        if Notification.objects.filter(recipient=recipient, booking=booking, notification_type=notification_type).exists():
            return None

    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        booking=booking,
        service=service,
        is_read=False,
    )


