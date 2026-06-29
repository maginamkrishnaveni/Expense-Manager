"""
MongoDB Models & Collection Initializer
----------------------------------------
Defines schemas for all collections and auto-creates them on server start.
"""

from datetime import datetime
from .db import get_db

# ── Collection Names ───────────────────────────────────────────
COLLECTION_EXPENSES     = 'expenses'
COLLECTION_CATEGORIES   = 'categories'
COLLECTION_BUDGETS      = 'budgets'
COLLECTION_SETTINGS     = 'settings'
COLLECTION_MEMBERS      = 'members'
COLLECTION_CONTRIBUTIONS = 'contributions'
COLLECTION_SHARED_EXP   = 'shared_expenses'
COLLECTION_SETTLEMENTS  = 'settlements'
COLLECTION_REQUESTS     = 'reimbursement_requests'


# ══════════════════════════════════════════════════════════════
#  DEFAULT SEED DATA
# ══════════════════════════════════════════════════════════════

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

import hashlib

DEFAULT_MEMBERS = [
    {
        'name': 'Krishnaveni', 'role': 'admin',  'color': '#6366f1',
        'active': True,
        'username': 'krishnaveni',
        'password': hashlib.sha256('krishna123'.encode()).hexdigest(),
        'created_at': datetime.utcnow(),
    },
    {
        'name': 'Ananya', 'role': 'member', 'color': '#f59e0b',
        'active': True,
        'username': 'ananya',
        'password': hashlib.sha256('ananya123'.encode()).hexdigest(),
        'created_at': datetime.utcnow(),
    },
    {
        'name': 'Aiswarya', 'role': 'member', 'color': '#10b981',
        'active': True,
        'username': 'aiswarya',
        'password': hashlib.sha256('aiswarya123'.encode()).hexdigest(),
        'created_at': datetime.utcnow(),
    },
]

DEFAULT_SETTINGS = {
    'key':              'app_settings',
    'currency':         '₹',
    'currency_code':    'INR',
    'app_name':         'ExpenseIQ',
    'monthly_share':    8000,       # default contribution per person per month
    'created_at':       datetime.utcnow(),
}


# ══════════════════════════════════════════════════════════════
#  DOCUMENT SCHEMAS
# ══════════════════════════════════════════════════════════════

def expense_schema(title, amount, category, date_obj, note=''):
    """Personal expense record."""
    if not title or not title.strip():
        raise ValueError("Title is required.")
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    return {
        'title':      title.strip(),
        'amount':     round(float(amount), 2),
        'category':   category,
        'date':       date_obj,
        'day':        date_obj.day,
        'month':      date_obj.month,
        'year':       date_obj.year,
        'note':       note.strip(),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }


def shared_expense_schema(title, amount, category, date_obj,
                           paid_by, from_pool=True, note=''):
    """
    Shared flat expense.
    paid_by     : member name who physically paid
    from_pool   : True  → paid from the shared monthly pool
                  False → paid from personal pocket (to be recovered)
    """
    if not title or not title.strip():
        raise ValueError("Title is required.")
    if amount <= 0:
        raise ValueError("Amount must be greater than 0.")
    return {
        'title':      title.strip(),
        'amount':     round(float(amount), 2),
        'category':   category,
        'date':       date_obj,
        'day':        date_obj.day,
        'month':      date_obj.month,
        'year':       date_obj.year,
        'paid_by':    paid_by,
        'from_pool':  from_pool,    # False = admin paid from own pocket
        'note':       note.strip(),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }


def contribution_schema(member_name, amount, month, year, note=''):
    """Monthly share contribution from a member."""
    return {
        'member':     member_name,
        'amount':     round(float(amount), 2),
        'month':      int(month),
        'year':       int(year),
        'note':       note.strip(),
        'paid_on':    datetime.utcnow(),
        'created_at': datetime.utcnow(),
    }


def settlement_schema(paid_by, amount, description, date_obj, note=''):
    """
    A flatmate spent their own money on shared items.
    paid_by     : member name who spent their own money
    settled     : False = admin still owes them this amount
    """
    return {
        'paid_by':     paid_by,
        'amount':      round(float(amount), 2),
        'description': description.strip(),
        'date':        date_obj,
        'day':         date_obj.day,
        'month':       date_obj.month,
        'year':        date_obj.year,
        'settled':     False,
        'settled_on':  None,
        'note':        note.strip(),
        'created_at':  datetime.utcnow(),
    }


def reimbursement_request_schema(requested_by, amount, description, date_obj, note=''):
    """
    A flatmate requests reimbursement from admin for something they spent.
    status: 'pending' | 'approved' | 'rejected'
    """
    return {
        'requested_by': requested_by,
        'amount':       round(float(amount), 2),
        'description':  description.strip(),
        'date':         date_obj,
        'day':          date_obj.day,
        'month':        date_obj.month,
        'year':         date_obj.year,
        'status':       'pending',
        'admin_note':   '',
        'reviewed_on':  None,
        'note':         note.strip(),
        'created_at':   datetime.utcnow(),
    }


def budget_schema(category, amount, month, year):
    return {
        'category':   category,
        'amount':     round(float(amount), 2),
        'month':      int(month),
        'year':       int(year),
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
    }


# ══════════════════════════════════════════════════════════════
#  COLLECTION INITIALIZER
# ══════════════════════════════════════════════════════════════

def initialize_collections():
    """
    Called once on Django app startup via AppConfig.ready().
    Creates collections, indexes, and seeds default data.
    """
    db = get_db()
    existing = db.list_collection_names()

    # ── 1. expenses (personal) ─────────────────────────────────
    if COLLECTION_EXPENSES not in existing:
        db.create_collection(COLLECTION_EXPENSES)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_EXPENSES}'")
    col = db[COLLECTION_EXPENSES]
    col.create_index('year')
    col.create_index('month')
    col.create_index('category')
    col.create_index([('year', 1), ('month', 1)])
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_EXPENSES}'")

    # ── 2. categories ──────────────────────────────────────────
    if COLLECTION_CATEGORIES not in existing:
        db.create_collection(COLLECTION_CATEGORIES)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_CATEGORIES}'")
    col = db[COLLECTION_CATEGORIES]
    if col.count_documents({}) == 0:
        col.insert_many(DEFAULT_CATEGORIES)
        print(f"[ExpenseIQ] Seeded {len(DEFAULT_CATEGORIES)} default categories.")
    col.create_index('name', unique=True)
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_CATEGORIES}'")

    # ── 3. budgets ─────────────────────────────────────────────
    if COLLECTION_BUDGETS not in existing:
        db.create_collection(COLLECTION_BUDGETS)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_BUDGETS}'")
    col = db[COLLECTION_BUDGETS]
    col.create_index([('category', 1), ('month', 1), ('year', 1)], unique=True)
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_BUDGETS}'")

    # ── 4. settings ────────────────────────────────────────────
    if COLLECTION_SETTINGS not in existing:
        db.create_collection(COLLECTION_SETTINGS)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_SETTINGS}'")
    col = db[COLLECTION_SETTINGS]
    if col.count_documents({'key': 'app_settings'}) == 0:
        col.insert_one(DEFAULT_SETTINGS)
        print(f"[ExpenseIQ] Seeded default app settings.")
    col.create_index('key', unique=True)
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_SETTINGS}'")

    # ── 5. members ─────────────────────────────────────────────
    if COLLECTION_MEMBERS not in existing:
        db.create_collection(COLLECTION_MEMBERS)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_MEMBERS}'")
    col = db[COLLECTION_MEMBERS]
    if col.count_documents({}) == 0:
        col.insert_many(DEFAULT_MEMBERS)
        print(f"[ExpenseIQ] Seeded 3 default members.")
    else:
        # Add auth fields to existing members that don't have them
        import hashlib
        defaults = {m['username']: m for m in DEFAULT_MEMBERS}
        for member in col.find({}):
            if 'username' not in member:
                uname = member['name'].lower()
                if uname in defaults:
                    col.update_one(
                        {'_id': member['_id']},
                        {'$set': {
                            'username': defaults[uname]['username'],
                            'password': defaults[uname]['password'],
                        }}
                    )
    col.create_index('name', unique=True)
    col.create_index('username', unique=True)
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_MEMBERS}'")

    # ── 6. contributions ───────────────────────────────────────
    if COLLECTION_CONTRIBUTIONS not in existing:
        db.create_collection(COLLECTION_CONTRIBUTIONS)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_CONTRIBUTIONS}'")
    col = db[COLLECTION_CONTRIBUTIONS]
    col.create_index([('member', 1), ('month', 1), ('year', 1)])
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_CONTRIBUTIONS}'")

    # ── 7. shared_expenses ─────────────────────────────────────
    if COLLECTION_SHARED_EXP not in existing:
        db.create_collection(COLLECTION_SHARED_EXP)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_SHARED_EXP}'")
    col = db[COLLECTION_SHARED_EXP]
    col.create_index([('year', 1), ('month', 1)])
    col.create_index('paid_by')
    col.create_index('from_pool')
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_SHARED_EXP}'")

    # ── 8. settlements ─────────────────────────────────────────
    if COLLECTION_SETTLEMENTS not in existing:
        db.create_collection(COLLECTION_SETTLEMENTS)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_SETTLEMENTS}'")
    col = db[COLLECTION_SETTLEMENTS]
    col.create_index('paid_by')
    col.create_index('settled')
    col.create_index([('year', 1), ('month', 1)])
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_SETTLEMENTS}'")

    # ── 9. reimbursement_requests ──────────────────────────────
    if COLLECTION_REQUESTS not in existing:
        db.create_collection(COLLECTION_REQUESTS)
        print(f"[ExpenseIQ] Created collection: '{COLLECTION_REQUESTS}'")
    col = db[COLLECTION_REQUESTS]
    col.create_index('requested_by')
    col.create_index('status')
    col.create_index([('year', 1), ('month', 1)])
    print(f"[ExpenseIQ] Indexes ready: '{COLLECTION_REQUESTS}'")

    print("[ExpenseIQ] ✅ All collections initialized successfully.")
