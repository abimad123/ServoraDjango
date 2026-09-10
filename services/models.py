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

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='bookings')
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bookings')
    booking_date = models.DateField()
    booking_time = models.TimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
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
        help_text="Calculated platform revenue earned on completion"
    )
    address = models.TextField(blank=True, default='')
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Automatically calculate platform commission amount (e.g. 10% of total)
        if self.total_amount:
            self.commission_amount = (Decimal(self.total_amount) * (Decimal(self.commission_rate) / Decimal(100))).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    @property
    def provider_earning(self):
        """Returns the net take-home earnings for the provider after 10% platform fee."""
        if self.total_amount and self.commission_amount:
            return self.total_amount - self.commission_amount
        return Decimal('0.00')

    def __str__(self):
        return f"Booking #{self.id}: {self.service.title} by {self.customer.username} ({self.get_status_display()})"



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
        ('featured', 'Featured Listing'),
    )
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('failed', 'Failed'),
    )

    revenue_type = models.CharField(max_length=20, choices=REVENUE_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    provider = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='revenue_transactions')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='revenue_transactions')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='revenue_transactions')
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
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

    def __str__(self):
        return f"[{self.get_revenue_type_display()}] ₹{self.amount} - {self.provider.user.username} ({self.created_at.strftime('%d %b %Y')})"

