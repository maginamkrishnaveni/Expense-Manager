"""
Simple session-based auth helpers using MongoDB members collection.
No Django ORM — pure pymongo.
"""

import hashlib
from functools import wraps
from django.shortcuts import redirect
from .db import get_collection
from .models import COLLECTION_MEMBERS


def hash_password(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def authenticate(username, password):
    """Return member doc if credentials match, else None."""
    col = get_collection(COLLECTION_MEMBERS)
    member = col.find_one({'username': username.lower().strip()})
    if member and member.get('password') == hash_password(password):
        return member
    return None


def get_logged_in_user(request):
    """Return member dict from session, or None."""
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
