from .models import Notification


def notifications_context(request):
    """
    Globally provides unread notification count and recent notifications
    to all templates when a user is authenticated.
    """
    if request.user.is_authenticated:
        user_notifications = Notification.objects.filter(recipient=request.user)
        unread_count = user_notifications.filter(is_read=False).count()
        recent = user_notifications[:5]
        return {
            'unread_notifications_count': unread_count,
            'recent_notifications': recent,
        }
    return {
        'unread_notifications_count': 0,
        'recent_notifications': [],
    }
