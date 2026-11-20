import json
from datetime import datetime, date
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import (
    Flat, FlatSettings, Member,
    Expense, Category, Contribution,
    SharedExpense, Settlement, ReimbursementRequest,
)
from .auth import authenticate, get_logged_in_user, login_required, admin_required

# ── AI Agent (lazy import so Django still boots if AI deps missing) ──
def _get_ai_agent():
    try:
        from .ai_agent import answer_question, get_smart_insights
        return answer_question, get_smart_insights
    except ImportError:
        return None, None

MONTH_NAMES = ['', 'January', 'February', 'March', 'April', 'May', 'June',
               'July', 'August', 'September', 'October', 'November', 'December']
MONTH_CHOICES = [(i, MONTH_NAMES[i]) for i in range(1, 13)]

MEMBER_COLORS = ['#f59e0b', '#10b981', '#3b82f6', '#ec4899',
                 '#8b5cf6', '#ef4444', '#06b6d4', '#84cc16']

DEFAULT_CATEGORIES = [
    'Food & Dining', 'Rent & Housing', 'Transport', 'Shopping',
    'Health & Medical', 'Entertainment', 'Education',
    'Utilities & Bills', 'Groceries', 'Other',
]

# ── helpers ────────────────────────────────────────────────────

def _get_flat(user):
    """Return Flat object for the logged-in user.
    Handles stale sessions where flat_id is None by looking up from Member table.
    """
    flat_id = user.get('flat_id')
    if flat_id is None:
        # Stale session — look up via Member
        try:
            member = Member.objects.get(pk=user['id'])
            if member.flat_id:
                return member.flat
        except Member.DoesNotExist:
            pass
        raise Flat.DoesNotExist("No flat assigned to this user. Please log out and log back in.")
    return Flat.objects.get(pk=flat_id)

def _get_monthly_share(flat):
    settings, _ = FlatSettings.objects.get_or_create(flat=flat)
    return settings.monthly_share

def _get_categories():
    cats = list(Category.objects.values_list('name', flat=True).order_by('name'))
    return cats if cats else DEFAULT_CATEGORIES

def _get_members(flat):
    return list(Member.objects.filter(flat=flat, active=True).order_by('name'))

def _serialize_expense(e):
    return {
        'id': e.id, 'title': e.title, 'amount': e.amount,
        'category': e.category, 'date': e.date.strftime('%Y-%m-%d'),
        'note': e.note,
    }

def _pool_summary(flat, month, year):
    monthly_share = _get_monthly_share(flat)
    contribs = Contribution.objects.filter(flat=flat, month=month, year=year)
    total_collected = sum(c.amount for c in contribs)
    contrib_map = {c.member: c.amount for c in contribs}
    shared = SharedExpense.objects.filter(flat=flat, date__month=month, date__year=year)
    pool_spent   = sum(e.amount for e in shared if e.from_pool)
    pocket_spent = sum(e.amount for e in shared if not e.from_pool)
    return {
        'monthly_share':   monthly_share,
        'total_collected': round(total_collected, 2),
        'contrib_map':     contrib_map,
        'pool_spent':      round(pool_spent, 2),
        'pocket_spent':    round(pocket_spent, 2),
        'pool_balance':    round(total_collected - pool_spent, 2),
    }


# ══════════════════════════════════════════════════════════════
#  AUTH
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
            request.session['user_id']    = member.id
            request.session['user_name']  = member.name
            request.session['user_role']  = member.role
            request.session['user_color'] = member.color
            request.session['flat_id']    = member.flat_id   # always fresh from DB
            request.session['flat_name']  = member.flat.name if member.flat else ''
            return redirect('dashboard' if member.role == 'admin' else 'member_dashboard')
        error = 'Invalid username or password.'
    return render(request, 'expenses/login.html', {'error': error})


def logout_view(request):
    request.session.flush()
    return redirect('login')

# ══════════════════════════════════════════════════════════════
#  ADMIN — PERSONAL DASHBOARD
# ══════════════════════════════════════════════════════════════

@admin_required
def dashboard(request):
    user       = get_logged_in_user(request)
    flat       = _get_flat(user)
    categories = _get_categories()
    today      = date.today()

    sel_month    = request.GET.get('month', '')
    sel_category = request.GET.get('category', '')
    sel_year     = request.GET.get('year', str(today.year))

    qs = Expense.objects.filter(flat=flat)
    if sel_month:
        qs = qs.filter(date__month=int(sel_month), date__year=int(sel_year))
    elif sel_year:
        qs = qs.filter(date__year=int(sel_year))
    if sel_category:
        qs = qs.filter(category=sel_category)

    expenses     = list(qs.order_by('-date'))
    total        = sum(e.amount for e in expenses)
    all_expenses = list(Expense.objects.filter(flat=flat))
    grand_total  = sum(e.amount for e in all_expenses)

    cur_month_total = sum(
        e.amount for e in all_expenses
        if e.date.month == today.month and e.date.year == today.year
    )
    cat_data = {}
    for e in all_expenses:
        cat_data[e.category] = cat_data.get(e.category, 0) + e.amount

    month_data = {m: 0 for m in range(1, 13)}
    for e in all_expenses:
        if e.date.year == today.year:
            month_data[e.date.month] += e.amount

    month_labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    month_values = [round(month_data[m], 2) for m in range(1, 13)]
    top_category = max(cat_data, key=cat_data.get) if cat_data else '—'

    years = sorted(set(Expense.objects.filter(flat=flat).values_list('date__year', flat=True)), reverse=True)
    if today.year not in years:
        years = [today.year] + list(years)

    context = {
        'user': user, 'expenses': [_serialize_expense(e) for e in expenses],
        'categories': categories, 'total': round(total, 2),
        'grand_total': round(grand_total, 2), 'cur_month_total': round(cur_month_total, 2),
        'top_category': top_category, 'expense_count': len(all_expenses),
        'cat_labels': json.dumps(list(cat_data.keys())),
        'cat_values': json.dumps([round(v, 2) for v in cat_data.values()]),
        'month_labels': json.dumps(month_labels), 'month_values': json.dumps(month_values),
        'sel_month': sel_month, 'sel_year': sel_year,
        'sel_category': sel_category, 'years': years, 'months': MONTH_CHOICES,
    }
    return render(request, 'expenses/dashboard.html', context)

# ── Personal Expense CRUD ─────────────────────────────────────

@admin_required
@require_POST
def add_expense(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        title    = request.POST.get('title', '').strip()
        if title and amount > 0:
            Expense.objects.create(
                flat=flat, title=title, amount=round(amount, 2),
                category=request.POST.get('category', 'Other'),
                date=exp_date, note=request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    return redirect('dashboard')


@admin_required
def get_expense(request, expense_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        e = Expense.objects.get(pk=expense_id, flat=flat)
        return JsonResponse(_serialize_expense(e))
    except Expense.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@admin_required
@require_POST
def edit_expense(request, expense_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        e        = Expense.objects.get(pk=expense_id, flat=flat)
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        e.title    = request.POST.get('title', '').strip()
        e.amount   = round(float(request.POST.get('amount', 0)), 2)
        e.category = request.POST.get('category', 'Other')
        e.date     = exp_date
        e.note     = request.POST.get('note', '').strip()
        e.save()
    except Exception:
        pass
    return redirect('dashboard')


@admin_required
@require_POST
def delete_expense(request, expense_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    Expense.objects.filter(pk=expense_id, flat=flat).delete()
    return redirect('dashboard')


# ══════════════════════════════════════════════════════════════
#  ANALYTICS
# ══════════════════════════════════════════════════════════════

@admin_required
def analytics(request):
    user         = get_logged_in_user(request)
    flat         = _get_flat(user)
    categories   = _get_categories()
    today        = date.today()
    all_expenses = list(Expense.objects.filter(flat=flat))

    yearly = {}
    for e in all_expenses:
        y = e.date.year
        yearly[y] = yearly.get(y, 0) + e.amount
    yearly_sorted = sorted(yearly.items())

    cat_month = {c: [0] * 12 for c in categories}
    for e in all_expenses:
        if e.date.year == today.year and e.category in cat_month:
            cat_month[e.category][e.date.month - 1] += e.amount

    daily = {}
    for e in all_expenses:
        if e.date.month == today.month and e.date.year == today.year:
            daily[e.date.day] = daily.get(e.date.day, 0) + e.amount
    daily_labels = sorted(daily.keys())
    daily_values = [round(daily[d], 2) for d in daily_labels]

    monthly_totals = {}
    for e in all_expenses:
        key = f'{e.date.year}-{e.date.month}'
        monthly_totals[key] = monthly_totals.get(key, 0) + e.amount
    avg_monthly = round(sum(monthly_totals.values()) / len(monthly_totals), 2) if monthly_totals else 0

    month_labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    colors = ['#FF6384','#36A2EB','#FFCE56','#4BC0C0','#9966FF','#FF9F40','#C9CBCF','#71B37C','#A4A4A4','#FF6B6B']
    stacked_datasets = [
        {'label': cat, 'data': [round(v, 2) for v in cat_month[cat]], 'backgroundColor': colors[i % len(colors)]}
        for i, cat in enumerate(categories)
    ]

    context = {
        'user': user,
        'yearly_labels':    json.dumps([str(y) for y, _ in yearly_sorted]),
        'yearly_values':    json.dumps([round(v, 2) for _, v in yearly_sorted]),
        'month_labels':     json.dumps(month_labels),
        'stacked_datasets': json.dumps(stacked_datasets),
        'daily_labels':     json.dumps(daily_labels),
        'daily_values':     json.dumps(daily_values),
        'avg_monthly':      avg_monthly,
        'total_expenses':   len(all_expenses),
        'grand_total':      round(sum(e.amount for e in all_expenses), 2),
        'categories':       categories,
    }
    return render(request, 'expenses/analytics.html', context)


# ══════════════════════════════════════════════════════════════
#  MEMBER DASHBOARD
# ══════════════════════════════════════════════════════════════

@login_required
def member_dashboard(request):
    user  = get_logged_in_user(request)
    flat  = _get_flat(user)
    today = date.today()
    sel_month = int(request.GET.get('month', today.month))
    sel_year  = int(request.GET.get('year',  today.year))

    pool            = _pool_summary(flat, sel_month, sel_year)
    my_contribution = pool['contrib_map'].get(user['name'], 0)
    my_balance      = my_contribution - pool['monthly_share']

    shared_expenses = list(
        SharedExpense.objects.filter(flat=flat, date__month=sel_month, date__year=sel_year)
        .order_by('-date').values()
    )
    for e in shared_expenses:
        e['date'] = e['date'].strftime('%Y-%m-%d') if e.get('date') else ''

    my_requests = list(
        ReimbursementRequest.objects.filter(
            flat=flat, requested_by=user['name'], month=sel_month, year=sel_year
        ).order_by('-created_at').values()
    )
    for r in my_requests:
        r['date'] = r['date'].strftime('%Y-%m-%d') if r.get('date') else ''

    # Charts: per-month contribution vs spending for this member
    all_contribs = list(Contribution.objects.filter(flat=flat, member=user['name']))
    contrib_by_month = [0] * 12
    for c in all_contribs:
        if c.year == today.year:
            contrib_by_month[c.month - 1] += c.amount

    # Flat total expenses per month for context
    flat_expenses_monthly = [0] * 12
    for e in SharedExpense.objects.filter(flat=flat, date__year=today.year):
        flat_expenses_monthly[e.date.month - 1] += e.amount

    month_labels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

    context = {
        'user':             user,
        'sel_month':        sel_month,
        'sel_year':         sel_year,
        'sel_month_name':   MONTH_NAMES[sel_month],
        'months':           MONTH_CHOICES,
        'years':            sorted({today.year, sel_year}, reverse=True),
        'pool':             pool,
        'my_contribution':  round(my_contribution, 2),
        'my_balance':       round(my_balance, 2),
        'shared_expenses':  shared_expenses,
        'my_requests':      my_requests,
        'pending_requests': [r for r in my_requests if r['status'] == 'pending'],
        'month_labels':     json.dumps(month_labels),
        'contrib_data':     json.dumps([round(v, 2) for v in contrib_by_month]),
        'flat_exp_data':    json.dumps([round(v, 2) for v in flat_expenses_monthly]),
    }
    return render(request, 'expenses/member_dashboard.html', context)


# ══════════════════════════════════════════════════════════════
#  REIMBURSEMENT REQUESTS
# ══════════════════════════════════════════════════════════════

@login_required
@require_POST
def submit_request(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        amount   = float(request.POST.get('amount', 0))
        req_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        ReimbursementRequest.objects.create(
            flat=flat, requested_by=user['name'],
            amount=round(amount, 2),
            description=request.POST.get('description', '').strip(),
            date=req_date, month=req_date.month, year=req_date.year,
            note=request.POST.get('note', '').strip(),
        )
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/member/?month={m}&year={y}')


@admin_required
@require_POST
def review_request(request, request_id):
    user   = get_logged_in_user(request)
    flat   = _get_flat(user)
    action = request.POST.get('action')
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    if action not in ('approve', 'reject'):
        return redirect(f'/flat/?month={m}&year={y}')
    try:
        req_obj = ReimbursementRequest.objects.get(pk=request_id, flat=flat)
        req_obj.status      = 'approved' if action == 'approve' else 'rejected'
        req_obj.admin_note  = request.POST.get('admin_note', '').strip()
        req_obj.reviewed_on = timezone.now()
        req_obj.save()
        if req_obj.status == 'approved':
            Settlement.objects.create(
                flat=flat, paid_by=req_obj.requested_by,
                amount=req_obj.amount, description=req_obj.description,
                date=req_obj.date, month=req_obj.month, year=req_obj.year,
                note=f'From approved request: {req_obj.note}',
            )
    except ReimbursementRequest.DoesNotExist:
        pass
    return redirect(f'/flat/?month={m}&year={y}')


# ══════════════════════════════════════════════════════════════
#  FLAT MANAGER  (admin only)
# ══════════════════════════════════════════════════════════════

@admin_required
def flat_manager(request):
    user      = get_logged_in_user(request)
    flat      = _get_flat(user)
    today     = date.today()
    sel_month = int(request.GET.get('month', today.month))
    sel_year  = int(request.GET.get('year',  today.year))

    pool         = _pool_summary(flat, sel_month, sel_year)
    members      = _get_members(flat)
    member_names = [m.name for m in members]
    categories   = _get_categories()

    shared_expenses = list(
        SharedExpense.objects.filter(flat=flat, date__month=sel_month, date__year=sel_year)
        .order_by('-date').values()
    )
    for e in shared_expenses:
        e['date'] = e['date'].strftime('%Y-%m-%d') if e.get('date') else ''

    total_shared     = sum(e['amount'] for e in shared_expenses)
    all_settlements  = list(Settlement.objects.filter(flat=flat, month=sel_month, year=sel_year).order_by('-date'))
    pending_settlements = [s for s in all_settlements if not s.settled]
    settled_settlements = [s for s in all_settlements if s.settled]
    total_pending    = sum(s.amount for s in pending_settlements)

    pending_requests = list(
        ReimbursementRequest.objects.filter(flat=flat, status='pending').order_by('-created_at').values()
    )
    for r in pending_requests:
        r['date'] = r['date'].strftime('%Y-%m-%d') if r.get('date') else ''

    member_summary = []
    for m in members:
        contributed       = pool['contrib_map'].get(m.name, 0)
        member_pending    = sum(s.amount for s in pending_settlements if s.paid_by == m.name)
        member_summary.append({
            'name': m.name, 'id': m.id, 'color': m.color, 'role': m.role,
            'contributed': contributed, 'share_due': pool['monthly_share'],
            'balance': contributed - pool['monthly_share'],
            'pending_owed': member_pending,
        })

    years_set = set(Contribution.objects.filter(flat=flat).values_list('year', flat=True))
    years_set |= set(SharedExpense.objects.filter(flat=flat).values_list('date__year', flat=True))
    years = sorted({today.year, sel_year} | years_set, reverse=True)

    flat_settings, _ = FlatSettings.objects.get_or_create(flat=flat)

    context = {
        'user': user, 'flat': flat, 'flat_settings': flat_settings,
        'members': members, 'member_names': member_names,
        'member_summary': member_summary, 'categories': categories,
        'sel_month': sel_month, 'sel_year': sel_year,
        'sel_month_name': MONTH_NAMES[sel_month],
        'years': years, 'months': MONTH_CHOICES, 'pool': pool,
        'monthly_share': pool['monthly_share'],
        'total_collected': pool['total_collected'],
        'pool_balance': pool['pool_balance'],
        'pool_expenses': pool['pool_spent'],
        'pocket_expenses': pool['pocket_spent'],
        'total_shared': round(total_shared, 2),
        'shared_expenses': shared_expenses,
        'pending_settlements': pending_settlements,
        'settled_settlements': settled_settlements,
        'total_pending': round(total_pending, 2),
        'pending_count': len(pending_settlements),
        'pending_requests': pending_requests,
        'request_count': len(pending_requests),
    }
    return render(request, 'expenses/flat_manager.html', context)


# ══════════════════════════════════════════════════════════════
#  REGISTER VIEW
# ══════════════════════════════════════════════════════════════

def register_view(request):
    if get_logged_in_user(request):
        return redirect('dashboard')
    error = ''
    if request.method == 'POST':
        flat_name  = request.POST.get('flat_name', '').strip()
        name       = request.POST.get('name', '').strip()
        username   = request.POST.get('username', '').strip().lower()
        password   = request.POST.get('password', '').strip()
        password2  = request.POST.get('password2', '').strip()
        if not all([flat_name, name, username, password]):
            error = 'All fields are required.'
        elif password != password2:
            error = 'Passwords do not match.'
        elif Member.objects.filter(username=username).exists():
            error = 'Username already taken. Choose another.'
        else:
            flat = Flat.objects.create(name=flat_name)
            FlatSettings.objects.create(flat=flat)
            Member.objects.create(
                flat=flat, name=name, username=username,
                password=Member.hash_password(password),
                role='admin', color='#6366f1', active=True,
            )
            if not Category.objects.exists():
                for cat_name in DEFAULT_CATEGORIES:
                    Category.objects.get_or_create(name=cat_name)
            return redirect('login')
    return render(request, 'expenses/register.html', {'error': error})


# ══════════════════════════════════════════════════════════════
#  AI CHAT AGENT
# ══════════════════════════════════════════════════════════════

@login_required
def ai_chat(request):
    """Render the AI chat page."""
    user = get_logged_in_user(request)
    return render(request, 'expenses/ai_chat.html', {'user': user})


@login_required
@require_POST
def ai_chat_api(request):
    """
    AJAX endpoint: POST { "question": "..." }
    Returns { "answer": "..." }
    """
    user = get_logged_in_user(request)
    try:
        body = json.loads(request.body)
        question = body.get('question', '').strip()
        if not question:
            return JsonResponse({'error': 'Question is required.'}, status=400)

        answer_fn, _ = _get_ai_agent()
        if answer_fn is None:
            return JsonResponse({
                'answer': '⚠️ AI dependencies not installed. Run: pip install langchain langchain-openai langgraph chromadb'
            })

        answer = answer_fn(
            flat_id=user['flat_id'],
            user_name=user['name'],
            question=question,
        )
        return JsonResponse({'answer': answer})
    except Exception as e:
        return JsonResponse({'answer': f'Error: {str(e)}'})


@login_required
def ai_insights_api(request):
    """
    GET endpoint: returns auto-generated spending insights for dashboard widget.
    Returns { "insights": [...] }
    """
    user = get_logged_in_user(request)
    _, insights_fn = _get_ai_agent()
    if insights_fn is None:
        return JsonResponse({'insights': []})

    insights = insights_fn(flat_id=user['flat_id'])
    return JsonResponse({'insights': insights})


# ══════════════════════════════════════════════════════════════
#  SETTINGS / MEMBER MANAGEMENT
# ══════════════════════════════════════════════════════════════

@admin_required
@require_POST
def add_contribution(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    try:
        amount = float(request.POST.get('amount', 0))
        member = request.POST.get('member', '').strip()
        if member and amount > 0:
            Contribution.objects.create(
                flat=flat, member=member, amount=round(amount, 2),
                month=int(request.POST.get('month', date.today().month)),
                year=int(request.POST.get('year',  date.today().year)),
                note=request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def add_shared_expense(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        title    = request.POST.get('title', '').strip()
        if title and amount > 0:
            SharedExpense.objects.create(
                flat=flat, title=title, amount=round(amount, 2),
                category=request.POST.get('category', 'Other'),
                date=exp_date,
                paid_by=request.POST.get('paid_by', '').strip(),
                from_pool=request.POST.get('from_pool', 'true') == 'true',
                note=request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def delete_shared_expense(request, expense_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    SharedExpense.objects.filter(pk=expense_id, flat=flat).delete()
    return redirect('flat_manager')


@admin_required
@require_POST
def add_settlement(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    try:
        amount   = float(request.POST.get('amount', 0))
        set_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        if amount > 0:
            Settlement.objects.create(
                flat=flat,
                paid_by=request.POST.get('paid_by', '').strip(),
                amount=round(amount, 2),
                description=request.POST.get('description', '').strip(),
                date=set_date,
                month=int(request.POST.get('month', date.today().month)),
                year=int(request.POST.get('year',  date.today().year)),
                note=request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def mark_settled(request, settlement_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    Settlement.objects.filter(pk=settlement_id, flat=flat).update(
        settled=True, settled_on=timezone.now()
    )
    return redirect('flat_manager')


@admin_required
@require_POST
def delete_settlement(request, settlement_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    Settlement.objects.filter(pk=settlement_id, flat=flat).delete()
    return redirect('flat_manager')


@admin_required
@require_POST
def update_member(request, member_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        member = Member.objects.get(pk=member_id, flat=flat)
        member.name   = request.POST.get('name', member.name).strip()
        member.color  = request.POST.get('color', member.color)
        member.active = request.POST.get('active', 'true') == 'true'
        member.save()
    except Member.DoesNotExist:
        pass
    return redirect('flat_manager')


@admin_required
@require_POST
def add_member(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        username = request.POST.get('username', '').strip().lower()
        name     = request.POST.get('name', '').strip()
        password = request.POST.get('password', '').strip()
        if username and name and password and not Member.objects.filter(username=username).exists():
            idx = Member.objects.filter(flat=flat).count() % len(MEMBER_COLORS)
            Member.objects.create(
                flat=flat, name=name, username=username,
                password=Member.hash_password(password),
                role='member',
                color=MEMBER_COLORS[idx],
                active=True,
            )
    except Exception:
        pass
    return redirect('flat_manager')


@admin_required
@require_POST
def delete_member(request, member_id):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    Member.objects.filter(pk=member_id, flat=flat, role='member').delete()
    return redirect('flat_manager')


@admin_required
@require_POST
def update_monthly_share(request):
    user = get_logged_in_user(request)
    flat = _get_flat(user)
    try:
        share = float(request.POST.get('monthly_share', 5000))
        settings, _ = FlatSettings.objects.get_or_create(flat=flat)
        settings.monthly_share = share
        settings.save()
    except Exception:
        pass
    return redirect('flat_manager')


@admin_required
@require_POST
def change_password(request):
    user = get_logged_in_user(request)
    try:
        member  = Member.objects.get(pk=user['id'])
        old_pwd = request.POST.get('old_password', '')
        new_pwd = request.POST.get('new_password', '')
        if member.password == Member.hash_password(old_pwd) and new_pwd:
            member.password = Member.hash_password(new_pwd)
            member.save()
    except Exception:
        pass
    return redirect('dashboard')
