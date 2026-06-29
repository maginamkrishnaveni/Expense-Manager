import json
from datetime import datetime, date
from bson import ObjectId
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .db import get_collection
from .auth import authenticate, get_logged_in_user, login_required, admin_required
from .models import (
    expense_schema, shared_expense_schema,
    contribution_schema, settlement_schema,
    reimbursement_request_schema,
    COLLECTION_EXPENSES, COLLECTION_CATEGORIES,
    COLLECTION_MEMBERS, COLLECTION_CONTRIBUTIONS,
    COLLECTION_SHARED_EXP, COLLECTION_SETTLEMENTS,
    COLLECTION_SETTINGS, COLLECTION_REQUESTS,
)

MONTH_NAMES   = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December']
MONTH_CHOICES = [(i, MONTH_NAMES[i]) for i in range(1, 13)]


# ── helpers ────────────────────────────────────────────────────
def _serialize(doc):
    doc['id'] = str(doc.pop('_id'))
    for field in ('date', 'settled_on', 'reviewed_on', 'paid_on'):
        if isinstance(doc.get(field), datetime):
            doc[field] = doc[field].strftime('%Y-%m-%d')
    return doc


def _get_categories():
    col  = get_collection(COLLECTION_CATEGORIES)
    cats = list(col.find({}, {'name': 1, '_id': 0}).sort('name', 1))
    return [c['name'] for c in cats] if cats else ['Other']


def _get_members():
    col     = get_collection(COLLECTION_MEMBERS)
    members = list(col.find({'active': True}).sort('name', 1))
    for m in members:
        m['id'] = str(m.pop('_id'))
    return members


def _get_monthly_share():
    col = get_collection(COLLECTION_SETTINGS)
    s   = col.find_one({'key': 'app_settings'})
    return s.get('monthly_share', 8000) if s else 8000


def _pool_summary(month, year):
    """Return pool KPIs for a given month/year."""
    monthly_share  = _get_monthly_share()
    contribs       = list(get_collection(COLLECTION_CONTRIBUTIONS).find(
        {'month': month, 'year': year}
    ))
    total_collected = sum(c['amount'] for c in contribs)
    contrib_map     = {c['member']: c['amount'] for c in contribs}

    shared = list(get_collection(COLLECTION_SHARED_EXP).find(
        {'month': month, 'year': year}
    ))
    pool_spent   = sum(e['amount'] for e in shared if e.get('from_pool'))
    pocket_spent = sum(e['amount'] for e in shared if not e.get('from_pool'))
    pool_balance = total_collected - pool_spent

    return {
        'monthly_share':   monthly_share,
        'total_collected': round(total_collected, 2),
        'contrib_map':     contrib_map,
        'pool_spent':      round(pool_spent, 2),
        'pocket_spent':    round(pocket_spent, 2),
        'pool_balance':    round(pool_balance, 2),
    }


# ══════════════════════════════════════════════════════════════
#  AUTH VIEWS
# ══════════════════════════════════════════════════════════════
def login_view(request):
    if get_logged_in_user(request):
        user = get_logged_in_user(request)
        return redirect('dashboard' if user['role'] == 'admin' else 'member_dashboard')

    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        member   = authenticate(username, password)
        if member:
            request.session['user_id']   = str(member['_id'])
            request.session['user_name'] = member['name']
            request.session['user_role'] = member['role']
            request.session['user_color'] = member.get('color', '#6366f1')
            if member['role'] == 'admin':
                return redirect('dashboard')
            return redirect('member_dashboard')
        error = 'Invalid username or password.'

    return render(request, 'expenses/login.html', {'error': error})


def logout_view(request):
    request.session.flush()
    return redirect('login')


# ══════════════════════════════════════════════════════════════
#  MEMBER DASHBOARD  (flatmates view)
# ══════════════════════════════════════════════════════════════
@login_required
def member_dashboard(request):
    user  = get_logged_in_user(request)
    today = date.today()

    sel_month = int(request.GET.get('month', today.month))
    sel_year  = int(request.GET.get('year',  today.year))

    pool = _pool_summary(sel_month, sel_year)

    # This member's contribution
    my_contribution = pool['contrib_map'].get(user['name'], 0)
    my_balance      = my_contribution - pool['monthly_share']

    # Shared expenses list (read-only for members)
    shared_expenses = list(get_collection(COLLECTION_SHARED_EXP).find(
        {'month': sel_month, 'year': sel_year}
    ).sort('date', -1))
    for e in shared_expenses:
        e['id'] = str(e.pop('_id'))
        if isinstance(e.get('date'), datetime):
            e['date'] = e['date'].strftime('%Y-%m-%d')

    # This member's reimbursement requests
    my_requests = list(get_collection(COLLECTION_REQUESTS).find(
        {'requested_by': user['name'], 'month': sel_month, 'year': sel_year}
    ).sort('created_at', -1))
    for r in my_requests:
        r['id'] = str(r.pop('_id'))
        if isinstance(r.get('date'), datetime):
            r['date'] = r['date'].strftime('%Y-%m-%d')

    # Available years
    years = sorted({today.year, sel_year}, reverse=True)

    context = {
        'user':             user,
        'sel_month':        sel_month,
        'sel_year':         sel_year,
        'sel_month_name':   MONTH_NAMES[sel_month],
        'months':           MONTH_CHOICES,
        'years':            years,
        'pool':             pool,
        'my_contribution':  round(my_contribution, 2),
        'my_balance':       round(my_balance, 2),
        'shared_expenses':  shared_expenses,
        'my_requests':      my_requests,
        'pending_requests': [r for r in my_requests if r['status'] == 'pending'],
    }
    return render(request, 'expenses/member_dashboard.html', context)


# ══════════════════════════════════════════════════════════════
#  REIMBURSEMENT REQUESTS
# ══════════════════════════════════════════════════════════════
@login_required
@require_POST
def submit_request(request):
    user = get_logged_in_user(request)
    try:
        amount   = float(request.POST.get('amount', 0))
        req_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
        doc = reimbursement_request_schema(
            requested_by = user['name'],
            amount       = amount,
            description  = request.POST.get('description', ''),
            date_obj     = req_date,
            note         = request.POST.get('note', ''),
        )
        get_collection(COLLECTION_REQUESTS).insert_one(doc)
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/member/?month={m}&year={y}')


@admin_required
@require_POST
def review_request(request, request_id):
    """Admin approves or rejects a reimbursement request."""
    action     = request.POST.get('action')   # 'approve' or 'reject'
    admin_note = request.POST.get('admin_note', '').strip()
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)

    if action not in ('approve', 'reject'):
        return redirect(f'/flat/?month={m}&year={y}')

    status = 'approved' if action == 'approve' else 'rejected'
    get_collection(COLLECTION_REQUESTS).update_one(
        {'_id': ObjectId(request_id)},
        {'$set': {
            'status':      status,
            'admin_note':  admin_note,
            'reviewed_on': datetime.utcnow(),
        }}
    )

    # If approved → auto-create a settlement record so it shows in pending dues
    if status == 'approved':
        req_doc = get_collection(COLLECTION_REQUESTS).find_one(
            {'_id': ObjectId(request_id)}
        )
        if req_doc:
            doc = settlement_schema(
                paid_by     = req_doc['requested_by'],
                amount      = req_doc['amount'],
                description = req_doc['description'],
                date_obj    = req_doc['date'],
                note        = f"Auto from approved request: {req_doc.get('note', '')}",
            )
            # carry month/year from the original request
            doc['month'] = req_doc['month']
            doc['year']  = req_doc['year']
            get_collection(COLLECTION_SETTLEMENTS).insert_one(doc)

    return redirect(f'/flat/?month={m}&year={y}')


# ══════════════════════════════════════════════════════════════
#  ADMIN — PERSONAL DASHBOARD
# ══════════════════════════════════════════════════════════════
@admin_required
def dashboard(request):
    col        = get_collection(COLLECTION_EXPENSES)
    categories = _get_categories()
    today      = date.today()

    sel_month    = request.GET.get('month', '')
    sel_category = request.GET.get('category', '')
    sel_year     = request.GET.get('year', str(today.year))

    query = {}
    if sel_month:
        query['month'] = int(sel_month)
        query['year']  = int(sel_year)
    elif sel_year:
        query['year'] = int(sel_year)
    if sel_category:
        query['category'] = sel_category

    expenses = list(col.find(query).sort('date', -1))
    for e in expenses:
        _serialize(e)

    total        = sum(e['amount'] for e in expenses)
    all_expenses = list(col.find())
    grand_total  = sum(e['amount'] for e in all_expenses)

    cur_month_total = sum(
        e['amount'] for e in all_expenses
        if e.get('month') == today.month and e.get('year') == today.year
    )
    cat_data = {}
    for e in all_expenses:
        c = e.get('category', 'Other')
        cat_data[c] = cat_data.get(c, 0) + e['amount']

    month_data = {m: 0 for m in range(1, 13)}
    for e in all_expenses:
        if e.get('year') == today.year:
            month_data[e.get('month', 1)] += e['amount']

    month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    month_values = [round(month_data[m], 2) for m in range(1, 13)]
    top_category = max(cat_data, key=cat_data.get) if cat_data else '—'

    years = sorted(set(e.get('year', today.year) for e in all_expenses), reverse=True)
    if today.year not in years:
        years.insert(0, today.year)

    context = {
        'user':            get_logged_in_user(request),
        'expenses':        expenses,
        'categories':      categories,
        'total':           round(total, 2),
        'grand_total':     round(grand_total, 2),
        'cur_month_total': round(cur_month_total, 2),
        'top_category':    top_category,
        'expense_count':   len(all_expenses),
        'cat_labels':      json.dumps(list(cat_data.keys())),
        'cat_values':      json.dumps([round(v, 2) for v in cat_data.values()]),
        'month_labels':    json.dumps(month_labels),
        'month_values':    json.dumps(month_values),
        'sel_month':       sel_month,
        'sel_year':        sel_year,
        'sel_category':    sel_category,
        'years':           years,
        'months':          MONTH_CHOICES,
    }
    return render(request, 'expenses/dashboard.html', context)


# ══════════════════════════════════════════════════════════════
#  PERSONAL EXPENSE CRUD
# ══════════════════════════════════════════════════════════════
@admin_required
@require_POST
def add_expense(request):
    col = get_collection(COLLECTION_EXPENSES)
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
        doc = expense_schema(
            title    = request.POST.get('title', ''),
            amount   = amount,
            category = request.POST.get('category', 'Other'),
            date_obj = exp_date,
            note     = request.POST.get('note', ''),
        )
        col.insert_one(doc)
    except Exception:
        pass
    return redirect('dashboard')


@admin_required
def get_expense(request, expense_id):
    col = get_collection(COLLECTION_EXPENSES)
    doc = col.find_one({'_id': ObjectId(expense_id)})
    if doc:
        return JsonResponse(_serialize(doc))
    return JsonResponse({'error': 'Not found'}, status=404)


@admin_required
@require_POST
def edit_expense(request, expense_id):
    col = get_collection(COLLECTION_EXPENSES)
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
        col.update_one(
            {'_id': ObjectId(expense_id)},
            {'$set': {
                'title':      request.POST.get('title', '').strip(),
                'amount':     round(amount, 2),
                'category':   request.POST.get('category', 'Other'),
                'date':       exp_date,
                'day':        exp_date.day,
                'month':      exp_date.month,
                'year':       exp_date.year,
                'note':       request.POST.get('note', '').strip(),
                'updated_at': datetime.utcnow(),
            }}
        )
    except Exception:
        pass
    return redirect('dashboard')


@admin_required
@require_POST
def delete_expense(request, expense_id):
    get_collection(COLLECTION_EXPENSES).delete_one({'_id': ObjectId(expense_id)})
    return redirect('dashboard')


# ══════════════════════════════════════════════════════════════
#  ANALYTICS
# ══════════════════════════════════════════════════════════════
@admin_required
def analytics(request):
    col          = get_collection(COLLECTION_EXPENSES)
    categories   = _get_categories()
    today        = date.today()
    all_expenses = list(col.find())

    yearly = {}
    for e in all_expenses:
        y = e.get('year', today.year)
        yearly[y] = yearly.get(y, 0) + e['amount']
    yearly_sorted = sorted(yearly.items())

    cat_month = {c: [0] * 12 for c in categories}
    for e in all_expenses:
        if e.get('year') == today.year:
            m = e.get('month', 1) - 1
            c = e.get('category', 'Other')
            if c in cat_month:
                cat_month[c][m] += e['amount']

    daily = {}
    for e in all_expenses:
        if e.get('month') == today.month and e.get('year') == today.year:
            d = e.get('day', 1)
            daily[d] = daily.get(d, 0) + e['amount']
    daily_labels = sorted(daily.keys())
    daily_values = [round(daily[d], 2) for d in daily_labels]

    monthly_totals = {}
    for e in all_expenses:
        key = f"{e.get('year')}-{e.get('month')}"
        monthly_totals[key] = monthly_totals.get(key, 0) + e['amount']
    avg_monthly = round(
        sum(monthly_totals.values()) / len(monthly_totals), 2
    ) if monthly_totals else 0

    month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    colors = ['#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', '#9966FF',
              '#FF9F40', '#C9CBCF', '#E7E9ED', '#71B37C', '#A4A4A4', '#FF6B6B']
    stacked_datasets = [
        {
            'label': cat,
            'data':  [round(v, 2) for v in cat_month[cat]],
            'backgroundColor': colors[i % len(colors)],
        }
        for i, cat in enumerate(categories)
    ]

    context = {
        'user':             get_logged_in_user(request),
        'yearly_labels':    json.dumps([str(y) for y, _ in yearly_sorted]),
        'yearly_values':    json.dumps([round(v, 2) for _, v in yearly_sorted]),
        'month_labels':     json.dumps(month_labels),
        'stacked_datasets': json.dumps(stacked_datasets),
        'daily_labels':     json.dumps(daily_labels),
        'daily_values':     json.dumps(daily_values),
        'avg_monthly':      avg_monthly,
        'total_expenses':   len(all_expenses),
        'grand_total':      round(sum(e['amount'] for e in all_expenses), 2),
        'categories':       categories,
    }
    return render(request, 'expenses/analytics.html', context)


# ══════════════════════════════════════════════════════════════
#  FLAT MANAGER  (admin only)
# ══════════════════════════════════════════════════════════════
@admin_required
def flat_manager(request):
    today        = date.today()
    sel_month    = int(request.GET.get('month', today.month))
    sel_year     = int(request.GET.get('year',  today.year))
    pool         = _pool_summary(sel_month, sel_year)
    members      = _get_members()
    member_names = [m['name'] for m in members]
    categories   = _get_categories()

    shared_expenses = list(get_collection(COLLECTION_SHARED_EXP).find(
        {'month': sel_month, 'year': sel_year}
    ).sort('date', -1))
    for e in shared_expenses:
        e['id'] = str(e.pop('_id'))
        if isinstance(e.get('date'), datetime):
            e['date'] = e['date'].strftime('%Y-%m-%d')

    total_shared = sum(e['amount'] for e in shared_expenses)

    all_settlements = list(get_collection(COLLECTION_SETTLEMENTS).find(
        {'month': sel_month, 'year': sel_year}
    ).sort('date', -1))
    for s in all_settlements:
        _serialize(s)

    pending_settlements = [s for s in all_settlements if not s.get('settled')]
    settled_settlements = [s for s in all_settlements if s.get('settled')]
    total_pending       = sum(s['amount'] for s in pending_settlements)

    # Pending reimbursement requests (admin review)
    pending_requests = list(get_collection(COLLECTION_REQUESTS).find(
        {'status': 'pending'}
    ).sort('created_at', -1))
    for r in pending_requests:
        r['id'] = str(r.pop('_id'))
        if isinstance(r.get('date'), datetime):
            r['date'] = r['date'].strftime('%Y-%m-%d')

    # Per-member summary
    member_summary = []
    for m in members:
        name = m['name']
        contributed         = pool['contrib_map'].get(name, 0)
        member_pending_amt  = sum(s['amount'] for s in pending_settlements if s['paid_by'] == name)
        member_summary.append({
            'name':         name,
            'id':           m['id'],
            'color':        m.get('color', '#6366f1'),
            'role':         m.get('role', 'member'),
            'contributed':  contributed,
            'share_due':    pool['monthly_share'],
            'balance':      contributed - pool['monthly_share'],
            'pending_owed': member_pending_amt,
        })

    all_years = {today.year, sel_year}
    for col_name in [COLLECTION_CONTRIBUTIONS, COLLECTION_SHARED_EXP]:
        for doc in get_collection(col_name).find({}, {'year': 1, '_id': 0}):
            all_years.add(doc.get('year', today.year))
    years = sorted(all_years, reverse=True)

    context = {
        'user':               get_logged_in_user(request),
        'members':            members,
        'member_names':       member_names,
        'member_summary':     member_summary,
        'categories':         categories,
        'sel_month':          sel_month,
        'sel_year':           sel_year,
        'sel_month_name':     MONTH_NAMES[sel_month],
        'years':              years,
        'months':             MONTH_CHOICES,
        'pool':               pool,
        'total_shared':       round(total_shared, 2),
        'shared_expenses':    shared_expenses,
        'pending_settlements': pending_settlements,
        'settled_settlements': settled_settlements,
        'total_pending':      round(total_pending, 2),
        'pending_count':      len(pending_settlements),
        'pending_requests':   pending_requests,
        'request_count':      len(pending_requests),
    }
    return render(request, 'expenses/flat_manager.html', context)


# ── Contribution ───────────────────────────────────────────────
@admin_required
@require_POST
def add_contribution(request):
    try:
        month  = int(request.POST.get('month'))
        year   = int(request.POST.get('year'))
        member = request.POST.get('member', '').strip()
        amount = float(request.POST.get('amount', 0))
        note   = request.POST.get('note', '')
        doc    = contribution_schema(member, amount, month, year, note)
        get_collection(COLLECTION_CONTRIBUTIONS).insert_one(doc)
    except Exception:
        pass
    return redirect(f'/flat/?month={request.POST.get("month")}&year={request.POST.get("year")}')


# ── Shared expense ─────────────────────────────────────────────
@admin_required
@require_POST
def add_shared_expense(request):
    try:
        amount    = float(request.POST.get('amount', 0))
        exp_date  = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
        from_pool = request.POST.get('from_pool', 'true') == 'true'
        doc = shared_expense_schema(
            title     = request.POST.get('title', ''),
            amount    = amount,
            category  = request.POST.get('category', 'Other'),
            date_obj  = exp_date,
            paid_by   = request.POST.get('paid_by', 'Krishnaveni'),
            from_pool = from_pool,
            note      = request.POST.get('note', ''),
        )
        get_collection(COLLECTION_SHARED_EXP).insert_one(doc)
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def delete_shared_expense(request, expense_id):
    doc = get_collection(COLLECTION_SHARED_EXP).find_one({'_id': ObjectId(expense_id)})
    m   = doc.get('month', date.today().month) if doc else date.today().month
    y   = doc.get('year',  date.today().year)  if doc else date.today().year
    get_collection(COLLECTION_SHARED_EXP).delete_one({'_id': ObjectId(expense_id)})
    return redirect(f'/flat/?month={m}&year={y}')


# ── Settlements ────────────────────────────────────────────────
@admin_required
@require_POST
def add_settlement(request):
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d')
        doc      = settlement_schema(
            paid_by     = request.POST.get('paid_by', ''),
            amount      = amount,
            description = request.POST.get('description', ''),
            date_obj    = exp_date,
            note        = request.POST.get('note', ''),
        )
        doc['month'] = exp_date.month
        doc['year']  = exp_date.year
        get_collection(COLLECTION_SETTLEMENTS).insert_one(doc)
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def mark_settled(request, settlement_id):
    get_collection(COLLECTION_SETTLEMENTS).update_one(
        {'_id': ObjectId(settlement_id)},
        {'$set': {'settled': True, 'settled_on': datetime.utcnow()}}
    )
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def delete_settlement(request, settlement_id):
    doc = get_collection(COLLECTION_SETTLEMENTS).find_one({'_id': ObjectId(settlement_id)})
    m   = doc.get('month', date.today().month) if doc else date.today().month
    y   = doc.get('year',  date.today().year)  if doc else date.today().year
    get_collection(COLLECTION_SETTLEMENTS).delete_one({'_id': ObjectId(settlement_id)})
    return redirect(f'/flat/?month={m}&year={y}')


# ── Member & settings management ──────────────────────────────
@admin_required
@require_POST
def update_member(request, member_id):
    new_name = request.POST.get('name', '').strip()
    new_pass = request.POST.get('password', '').strip()
    upd = {}
    if new_name:
        upd['name'] = new_name
    if new_pass:
        from .auth import hash_password
        upd['password'] = hash_password(new_pass)
    if upd:
        upd['updated_at'] = datetime.utcnow()
        get_collection(COLLECTION_MEMBERS).update_one(
            {'_id': ObjectId(member_id)}, {'$set': upd}
        )
    return redirect('flat_manager')


@admin_required
@require_POST
def update_monthly_share(request):
    try:
        amount = float(request.POST.get('monthly_share', 8000))
        get_collection(COLLECTION_SETTINGS).update_one(
            {'key': 'app_settings'},
            {'$set': {'monthly_share': amount}}
        )
    except Exception:
        pass
    return redirect('flat_manager')


# ── Change own password ────────────────────────────────────────
@login_required
@require_POST
def change_password(request):
    user     = get_logged_in_user(request)
    old_pass = request.POST.get('old_password', '')
    new_pass = request.POST.get('new_password', '').strip()
    from .auth import hash_password, authenticate
    member   = get_collection(COLLECTION_MEMBERS).find_one({'name': user['name']})
    if member and member.get('password') == hash_password(old_pass) and new_pass:
        get_collection(COLLECTION_MEMBERS).update_one(
            {'name': user['name']},
            {'$set': {'password': hash_password(new_pass)}}
        )
    role = user['role']
    return redirect('dashboard' if role == 'admin' else 'member_dashboard')
