from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from .forms import UserRegisterForm, UserLoginForm


def register_view(request):
    """
    Handles registration for both Customers and Service Providers.
    Accepts an optional ?role=provider query parameter to pre-select the provider option.
    """
    if request.user.is_authenticated:
        if request.user.profile.is_provider:
            return redirect('provider_dashboard')
        return redirect('home')

    preselected_role = request.GET.get('role', 'customer')
    if preselected_role not in ['customer', 'provider']:
        preselected_role = 'customer'

    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Log the newly registered user in immediately
            login(request, user)
            role_label = user.profile.get_role_display()
            messages.success(request, f"Welcome to Servora, {user.first_name}! Your {role_label} account has been created.")
            if user.profile.is_provider:
                return redirect('provider_dashboard')
            return redirect('home')
        else:
            messages.error(request, "Please correct the errors below to complete registration.")
    else:
        form = UserRegisterForm(initial={'role': preselected_role})

    return render(request, 'users/register.html', {
        'form': form,
        'selected_role': preselected_role,
    })


def login_view(request):
    """
    Authenticates existing users and routes them to their relevant role workspace.
    """
    if request.user.is_authenticated:
        if request.user.profile.is_provider:
            return redirect('provider_dashboard')
        return redirect('home')

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                name = user.first_name or user.username
                messages.success(request, f"Welcome back, {name}!")

                if next_url:
                    return redirect(next_url)
                if user.profile.is_provider:
                    return redirect('provider_dashboard')
                return redirect('home')
            else:
                messages.error(request, "Invalid username or password. Please try again.")
    else:
        form = UserLoginForm()

    return render(request, 'users/login.html', {
        'form': form,
        'next_url': next_url,
    })


def logout_view(request):
    """
    Logs out the user and redirects to the home page with a confirmation toast.
    """
    logout(request)
    messages.info(request, "You have been logged out successfully. Have a great day!")
    return redirect('home')
