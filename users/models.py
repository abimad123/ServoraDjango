from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class UserProfile(models.Model):
    """
    Extends Django's User model with role information, verification status,
    location, and profile details for both Customers and Providers.
    """
    ROLE_CHOICES = (
        ('customer', 'Customer / Homeowner'),
        ('provider', 'Service Provider / Professional'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=20, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='Kannur')
    address = models.TextField(blank=True, default='')
    bio = models.TextField(blank=True, default='')
    is_verified = models.BooleanField(default=False, help_text="Designates whether this provider has been verified.")
    avatar = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_role_display()})"

    @property
    def is_provider(self):
        return self.role == 'provider'

    @property
    def is_customer(self):
        return self.role == 'customer'

    @property
    def completed_jobs_count(self):
        from services.models import Booking
        return Booking.objects.filter(service__provider=self, status='completed').count()

    @property
    def average_rating(self):
        from services.models import Review
        from django.db.models import Avg
        avg_val = Review.objects.filter(service__provider=self).aggregate(Avg('rating'))['rating__avg']
        if avg_val is not None:
            return round(avg_val, 1)
        return 5.0

    @property
    def total_reviews_count(self):
        from services.models import Review
        return Review.objects.filter(service__provider=self).count()

    @property
    def is_pro(self):
        active_sub = self.subscriptions.filter(is_active=True).order_by('-id').first()
        return bool(active_sub and active_sub.plan_name == 'pro')


class ProviderSubscription(models.Model):
    """
    Tracks monthly subscription plans (e.g. Free vs Pro at ₹399/mo)
    for revenue calculations and provider feature unlocks.
    """
    PLAN_CHOICES = (
        ('free', 'Free Plan'),
        ('pro', 'Pro Plan (₹399/month)'),
    )

    provider = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='subscriptions')
    plan_name = models.CharField(max_length=50, choices=PLAN_CHOICES, default='free')
    monthly_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.provider.user.username} - {self.get_plan_name_display()} (₹{self.monthly_fee})"


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Ensures that a UserProfile instance is automatically created whenever a User is created.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
