from django.contrib import admin
from .models import UserProfile, ProviderSubscription


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'city', 'phone', 'is_verified', 'created_at')
    list_filter = ('role', 'is_verified', 'city')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'phone', 'city')
    list_editable = ('is_verified',)


@admin.register(ProviderSubscription)
class ProviderSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('provider', 'plan_name', 'monthly_fee', 'start_date', 'end_date', 'is_active')
    list_filter = ('plan_name', 'is_active')
    search_fields = ('provider__user__username', 'plan_name')
