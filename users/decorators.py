from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages


def provider_required(view_func):
    """
    Decorator to ensure the authenticated user has a 'provider' role.
    If not, redirects to the homepage with a warning message.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in to access the provider dashboard.")
            return redirect('login')
        if not hasattr(request.user, 'profile') or not request.user.profile.is_provider:
            messages.error(request, "Access restricted: This area is only available for service providers.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def customer_required(view_func):
    """
    Decorator to ensure the user is logged in.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.info(request, "Please log in to complete your booking.")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def admin_required(view_func):
    """
    Decorator to ensure the authenticated user has staff or superuser privileges.
    Protects the platform revenue and executive administration routes.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.warning(request, "Please log in with administrator credentials.")
            return redirect(f"{reverse('login')}?next={request.path}")
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, "Access restricted: Platform Revenue Dashboard is only accessible by platform administrators.")
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

