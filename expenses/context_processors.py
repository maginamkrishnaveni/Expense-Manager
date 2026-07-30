from .models import Settlement, ReimbursementRequest
from .auth import get_logged_in_user


def flat_context(request):
    """Injects pending counts and logged-in user into every template."""
    user          = get_logged_in_user(request)
    pending_count = 0
    request_count = 0

    if user:
        try:
            pending_count = Settlement.objects.filter(settled=False).count()
        except Exception:
            pass
        try:
            request_count = ReimbursementRequest.objects.filter(status='pending').count()
        except Exception:
            pass

    return {
        'pending_count': pending_count,
        'request_count': request_count,
        'current_user':  user,
    }
