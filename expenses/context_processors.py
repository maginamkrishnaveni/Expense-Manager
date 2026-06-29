from .db import get_collection
from .models import COLLECTION_SETTLEMENTS, COLLECTION_REQUESTS
from .auth import get_logged_in_user


def flat_context(request):
    """Injects pending counts and logged-in user into every template."""
    user = get_logged_in_user(request)
    pending_count  = 0
    request_count  = 0

    if user:
        try:
            pending_count = get_collection(COLLECTION_SETTLEMENTS).count_documents(
                {'settled': False}
            )
        except Exception:
            pass
        try:
            request_count = get_collection(COLLECTION_REQUESTS).count_documents(
                {'status': 'pending'}
            )
        except Exception:
            pass

    return {
        'pending_count': pending_count,
        'request_count': request_count,
        'current_user':  user,
    }
