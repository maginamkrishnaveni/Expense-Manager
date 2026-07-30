"""
Seeds default categories, members, and app settings into SQLite
on first run. Safe to call multiple times — skips if data exists.
"""

from .models import Member, Category, AppSettings


DEFAULT_CATEGORIES = [
    {'name': 'Food & Dining',        'icon': 'bi-cup-hot',          'color': '#FF6384'},
    {'name': 'Rent & Housing',       'icon': 'bi-house',            'color': '#36A2EB'},
    {'name': 'Transport',            'icon': 'bi-car-front',        'color': '#FFCE56'},
    {'name': 'Shopping',             'icon': 'bi-bag',              'color': '#4BC0C0'},
    {'name': 'Health & Medical',     'icon': 'bi-heart-pulse',      'color': '#9966FF'},
    {'name': 'Entertainment',        'icon': 'bi-camera-video',     'color': '#FF9F40'},
    {'name': 'Education',            'icon': 'bi-book',             'color': '#C9CBCF'},
    {'name': 'Utilities & Bills',    'icon': 'bi-lightning-charge', 'color': '#71B37C'},
    {'name': 'Savings & Investment', 'icon': 'bi-piggy-bank',       'color': '#A4A4A4'},
    {'name': 'Groceries',            'icon': 'bi-basket',           'color': '#FF6B6B'},
    {'name': 'Other',                'icon': 'bi-three-dots',       'color': '#E7E9ED'},
]

DEFAULT_MEMBERS = [
    {
        'name': 'Krishnaveni', 'role': 'admin',  'color': '#6366f1',
        'username': 'krishnaveni', 'password': 'krishna123',
    },
    {
        'name': 'Ananya', 'role': 'member', 'color': '#f59e0b',
        'username': 'ananya', 'password': 'ananya123',
    },
    {
        'name': 'Aiswarya', 'role': 'member', 'color': '#10b981',
        'username': 'aiswarya', 'password': 'aiswarya123',
    },
]


def seed_default_data():
    # Categories
    if not Category.objects.exists():
        for cat in DEFAULT_CATEGORIES:
            Category.objects.get_or_create(name=cat['name'], defaults={
                'icon': cat['icon'], 'color': cat['color']
            })
        print('[ExpenseIQ] Seeded default categories.')

    # Members
    if not Member.objects.exists():
        for m in DEFAULT_MEMBERS:
            Member.objects.get_or_create(username=m['username'], defaults={
                'name':     m['name'],
                'role':     m['role'],
                'color':    m['color'],
                'password': Member.hash_password(m['password']),
                'active':   True,
            })
        print('[ExpenseIQ] Seeded default members.')

    # App settings (single row)
    if not AppSettings.objects.exists():
        AppSettings.objects.create()
        print('[ExpenseIQ] Seeded default app settings.')

    print('[ExpenseIQ] ✅ Database ready.')
