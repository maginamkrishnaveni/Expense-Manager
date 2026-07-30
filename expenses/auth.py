"""
Session-based auth helpers using Django ORM (SQLite).
"""

import hashlib
from functools import wraps
from django.shortcuts import redirect
from .models import Member


def hash_password(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def authenticate(username, password):
    """Return Member instance if credentials match, else None."""
    try:
        member = Member.objects.get(username=username.lower().strip(), active=True)
        if member.password == hash_password(password):
            return member
    except Member.DoesNotExist:
        pass
    return None


def get_logged_in_user(request):
    """Return user dict from session, or None."""
    user_id = request.session.get('user_id')
    name    = request.session.get('user_name')
    role    = request.session.get('user_role')
    if user_id and name and role:
        return {'id': user_id, 'name': name, 'role': role}
    return None


def login_required(view_func):
    """Decorator — redirects to login if not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not get_logged_in_user(request):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    """Decorator — redirects to member dashboard if not admin."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = get_logged_in_user(request)
        if not user:
            return redirect('login')
        if user['role'] != 'admin':
            return redirect('member_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper
