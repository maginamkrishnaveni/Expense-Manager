import json
from datetime import datetime, date
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import (
    Expense, Category, Member, Contribution,
    SharedExpense, Settlement, ReimbursementRequest, AppSettings,
)
from .auth import authenticate, get_logged_in_user, login_required, admin_required

MONTH_NAMES = ['', 'January', 'February', 'March', 'April', 'May', 'June',
               'July', 'August', 'September', 'October', 'November', 'December']
MONTH_CHOICES = [(i, MONTH_NAMES[i]) for i in range(1, 13)]


# ── helpers ────────────────────────────────────────────────────

def _serialize_expense(e):
    return {
        'id':         e.id,
        'title':      e.title,
        'amount':     e.amount,
        'category':   e.category,
        'date':       e.date.strftime('%Y-%m-%d'),
        'note':       e.note,
        'created_at': e.created_at.strftime('%Y-%m-%d'),
    }


def _get_categories():
    cats = list(Category.objects.values_list('name', flat=True).order_by('name'))
    return cats if cats else ['Other']


def _get_members():
    return list(Member.objects.filter(active=True).order_by('name'))


def _get_monthly_share():
    settings = AppSettings.objects.first()
    return settings.monthly_share if settings else 8000


def _pool_summary(month, year):
    """Return pool KPIs for a given month/year."""
    monthly_share = _get_monthly_share()

    contribs = Contribution.objects.filter(month=month, year=year)
    total_collected = sum(c.amount for c in contribs)
    contrib_map = {c.member: c.amount for c in contribs}

    shared = SharedExpense.objects.filter(
        date__month=month, date__year=year
    )
    pool_spent   = sum(e.amount for e in shared if e.from_pool)
    pocket_spent = sum(e.amount for e in shared if not e.from_pool)
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
            request.session['user_id']    = member.id
            request.session['user_name']  = member.name
            request.session['user_role']  = member.role
            request.session['user_color'] = member.color
            if member.role == 'admin':
                return redirect('dashboard')
            return redirect('member_dashboard')
        error = 'Invalid username or password.'

    return render(request, 'expenses/login.html', {'error': error})


def logout_view(request):
    request.session.flush()
    return redirect('login')


# ══════════════════════════════════════════════════════════════
#  MEMBER DASHBOARD
# ══════════════════════════════════════════════════════════════

@login_required
def member_dashboard(request):
    user  = get_logged_in_user(request)
    today = date.today()

    sel_month = int(request.GET.get('month', today.month))
    sel_year  = int(request.GET.get('year',  today.year))

    pool            = _pool_summary(sel_month, sel_year)
    my_contribution = pool['contrib_map'].get(user['name'], 0)
    my_balance      = my_contribution - pool['monthly_share']

    shared_expenses = list(
        SharedExpense.objects.filter(
            date__month=sel_month, date__year=sel_year
        ).order_by('-date').values()
    )
    for e in shared_expenses:
        e['date'] = e['date'].strftime('%Y-%m-%d') if e.get('date') else ''

    my_requests = list(
        ReimbursementRequest.objects.filter(
            requested_by=user['name'], month=sel_month, year=sel_year
        ).order_by('-created_at').values()
    )
    for r in my_requests:
        r['date'] = r['date'].strftime('%Y-%m-%d') if r.get('date') else ''

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
        req_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        ReimbursementRequest.objects.create(
            requested_by = user['name'],
            amount       = round(amount, 2),
            description  = request.POST.get('description', '').strip(),
            date         = req_date,
            month        = req_date.month,
            year         = req_date.year,
            note         = request.POST.get('note', '').strip(),
        )
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/member/?month={m}&year={y}')


@admin_required
@require_POST
def review_request(request, request_id):
    action     = request.POST.get('action')
    admin_note = request.POST.get('admin_note', '').strip()
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)

    if action not in ('approve', 'reject'):
        return redirect(f'/flat/?month={m}&year={y}')

    try:
        req_obj = ReimbursementRequest.objects.get(pk=request_id)
        req_obj.status      = 'approved' if action == 'approve' else 'rejected'
        req_obj.admin_note  = admin_note
        req_obj.reviewed_on = timezone.now()
        req_obj.save()

        # Auto-create settlement when approved
        if req_obj.status == 'approved':
            Settlement.objects.create(
                paid_by     = req_obj.requested_by,
                amount      = req_obj.amount,
                description = req_obj.description,
                date        = req_obj.date,
                month       = req_obj.month,
                year        = req_obj.year,
                note        = f'Auto from approved request: {req_obj.note}',
            )
    except ReimbursementRequest.DoesNotExist:
        pass

    return redirect(f'/flat/?month={m}&year={y}')


# ══════════════════════════════════════════════════════════════
#  ADMIN — PERSONAL DASHBOARD
# ══════════════════════════════════════════════════════════════

@admin_required
def dashboard(request):
    categories = _get_categories()
    today      = date.today()

    sel_month    = request.GET.get('month', '')
    sel_category = request.GET.get('category', '')
    sel_year     = request.GET.get('year', str(today.year))

    qs = Expense.objects.all()
    if sel_month:
        qs = qs.filter(date__month=int(sel_month), date__year=int(sel_year))
    elif sel_year:
        qs = qs.filter(date__year=int(sel_year))
    if sel_category:
        qs = qs.filter(category=sel_category)

    expenses = list(qs.order_by('-date'))

    total        = sum(e.amount for e in expenses)
    all_expenses = list(Expense.objects.all())
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

    month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    month_values = [round(month_data[m], 2) for m in range(1, 13)]
    top_category = max(cat_data, key=cat_data.get) if cat_data else '—'

    years = sorted(
        set(Expense.objects.values_list('date__year', flat=True)),
        reverse=True
    )
    if today.year not in years:
        years = [today.year] + list(years)

    context = {
        'user':            get_logged_in_user(request),
        'expenses':        [_serialize_expense(e) for e in expenses],
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
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        title    = request.POST.get('title', '').strip()
        if title and amount > 0:
            Expense.objects.create(
                title    = title,
                amount   = round(amount, 2),
                category = request.POST.get('category', 'Other'),
                date     = exp_date,
                note     = request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    return redirect('dashboard')


@admin_required
def get_expense(request, expense_id):
    try:
        e = Expense.objects.get(pk=expense_id)
        return JsonResponse(_serialize_expense(e))
    except Expense.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)


@admin_required
@require_POST
def edit_expense(request, expense_id):
    try:
        e        = Expense.objects.get(pk=expense_id)
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        e.title    = request.POST.get('title', '').strip()
        e.amount   = round(amount, 2)
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
    Expense.objects.filter(pk=expense_id).delete()
    return redirect('dashboard')


# ══════════════════════════════════════════════════════════════
#  ANALYTICS
# ══════════════════════════════════════════════════════════════

@admin_required
def analytics(request):
    categories   = _get_categories()
    today        = date.today()
    all_expenses = list(Expense.objects.all())

    yearly = {}
    for e in all_expenses:
        y = e.date.year
        yearly[y] = yearly.get(y, 0) + e.amount
    yearly_sorted = sorted(yearly.items())

    cat_month = {c: [0] * 12 for c in categories}
    for e in all_expenses:
        if e.date.year == today.year:
            m = e.date.month - 1
            c = e.category
            if c in cat_month:
                cat_month[c][m] += e.amount

    daily = {}
    for e in all_expenses:
        if e.date.month == today.month and e.date.year == today.year:
            d = e.date.day
            daily[d] = daily.get(d, 0) + e.amount
    daily_labels = sorted(daily.keys())
    daily_values = [round(daily[d], 2) for d in daily_labels]

    monthly_totals = {}
    for e in all_expenses:
        key = f'{e.date.year}-{e.date.month}'
        monthly_totals[key] = monthly_totals.get(key, 0) + e.amount
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
        'grand_total':      round(sum(e.amount for e in all_expenses), 2),
        'categories':       categories,
    }
    return render(request, 'expenses/analytics.html', context)


# ══════════════════════════════════════════════════════════════
#  FLAT MANAGER  (admin only)
# ══════════════════════════════════════════════════════════════

@admin_required
def flat_manager(request):
    today     = date.today()
    sel_month = int(request.GET.get('month', today.month))
    sel_year  = int(request.GET.get('year',  today.year))

    pool         = _pool_summary(sel_month, sel_year)
    members      = _get_members()
    member_names = [m.name for m in members]
    categories   = _get_categories()

    shared_expenses = list(
        SharedExpense.objects.filter(
            date__month=sel_month, date__year=sel_year
        ).order_by('-date').values()
    )
    for e in shared_expenses:
        e['date'] = e['date'].strftime('%Y-%m-%d') if e.get('date') else ''

    total_shared = sum(e['amount'] for e in shared_expenses)

    all_settlements = list(
        Settlement.objects.filter(month=sel_month, year=sel_year).order_by('-date')
    )
    pending_settlements = [s for s in all_settlements if not s.settled]
    settled_settlements = [s for s in all_settlements if s.settled]
    total_pending       = sum(s.amount for s in pending_settlements)

    pending_requests = list(
        ReimbursementRequest.objects.filter(status='pending').order_by('-created_at').values()
    )
    for r in pending_requests:
        r['date'] = r['date'].strftime('%Y-%m-%d') if r.get('date') else ''

    member_summary = []
    for m in members:
        contributed        = pool['contrib_map'].get(m.name, 0)
        member_pending_amt = sum(
            s.amount for s in pending_settlements if s.paid_by == m.name
        )
        member_summary.append({
            'name':         m.name,
            'id':           m.id,
            'color':        m.color,
            'role':         m.role,
            'contributed':  contributed,
            'share_due':    pool['monthly_share'],
            'balance':      contributed - pool['monthly_share'],
            'pending_owed': member_pending_amt,
        })

    years_contrib = set(Contribution.objects.values_list('year', flat=True))
    years_shared  = set(SharedExpense.objects.values_list('date__year', flat=True))
    years = sorted({today.year, sel_year} | years_contrib | years_shared, reverse=True)

    context = {
        'user':                get_logged_in_user(request),
        'members':             members,
        'member_names':        member_names,
        'member_summary':      member_summary,
        'categories':          categories,
        'sel_month':           sel_month,
        'sel_year':            sel_year,
        'sel_month_name':      MONTH_NAMES[sel_month],
        'years':               years,
        'months':              MONTH_CHOICES,
        'pool':                pool,
        'total_shared':        round(total_shared, 2),
        'shared_expenses':     shared_expenses,
        'pending_settlements': pending_settlements,
        'settled_settlements': settled_settlements,
        'total_pending':       round(total_pending, 2),
        'pending_count':       len(pending_settlements),
        'pending_requests':    pending_requests,
        'request_count':       len(pending_requests),
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
        note   = request.POST.get('note', '').strip()
        if member and amount > 0:
            Contribution.objects.create(
                member=member, amount=round(amount, 2),
                month=month, year=year, note=note,
            )
    except Exception:
        pass
    return redirect(f'/flat/?month={request.POST.get("month")}&year={request.POST.get("year")}')


# ── Shared expense ─────────────────────────────────────────────

@admin_required
@require_POST
def add_shared_expense(request):
    try:
        amount    = float(request.POST.get('amount', 0))
        exp_date  = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        from_pool = request.POST.get('from_pool', 'true') == 'true'
        title     = request.POST.get('title', '').strip()
        if title and amount > 0:
            SharedExpense.objects.create(
                title     = title,
                amount    = round(amount, 2),
                category  = request.POST.get('category', 'Other'),
                date      = exp_date,
                paid_by   = request.POST.get('paid_by', 'Krishnaveni'),
                from_pool = from_pool,
                note      = request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def delete_shared_expense(request, expense_id):
    try:
        exp = SharedExpense.objects.get(pk=expense_id)
        m, y = exp.date.month, exp.date.year
        exp.delete()
    except SharedExpense.DoesNotExist:
        m, y = date.today().month, date.today().year
    return redirect(f'/flat/?month={m}&year={y}')


# ── Settlements ────────────────────────────────────────────────

@admin_required
@require_POST
def add_settlement(request):
    try:
        amount   = float(request.POST.get('amount', 0))
        exp_date = datetime.strptime(request.POST.get('date'), '%Y-%m-%d').date()
        paid_by  = request.POST.get('paid_by', '').strip()
        desc     = request.POST.get('description', '').strip()
        if paid_by and amount > 0:
            Settlement.objects.create(
                paid_by     = paid_by,
                amount      = round(amount, 2),
                description = desc,
                date        = exp_date,
                month       = exp_date.month,
                year        = exp_date.year,
                note        = request.POST.get('note', '').strip(),
            )
    except Exception:
        pass
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def mark_settled(request, settlement_id):
    Settlement.objects.filter(pk=settlement_id).update(
        settled=True, settled_on=timezone.now()
    )
    m = request.POST.get('month', date.today().month)
    y = request.POST.get('year',  date.today().year)
    return redirect(f'/flat/?month={m}&year={y}')


@admin_required
@require_POST
def delete_settlement(request, settlement_id):
    try:
        s = Settlement.objects.get(pk=settlement_id)
        m, y = s.month, s.year
        s.delete()
    except Settlement.DoesNotExist:
        m, y = date.today().month, date.today().year
    return redirect(f'/flat/?month={m}&year={y}')


# ── Member & settings management ──────────────────────────────

@admin_required
@require_POST
def update_member(request, member_id):
    try:
        member   = Member.objects.get(pk=member_id)
        new_name = request.POST.get('name', '').strip()
        new_pass = request.POST.get('password', '').strip()
        if new_name:
            member.name = new_name
        if new_pass:
            member.password = Member.hash_password(new_pass)
        member.save()
    except Member.DoesNotExist:
        pass
    return redirect('flat_manager')


@admin_required
@require_POST
def add_member(request):
    name     = request.POST.get('name', '').strip()
    username = request.POST.get('username', '').strip().lower()
    password = request.POST.get('password', '').strip()
    if name and username and password:
        colors = ['#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#8b5cf6', '#ef4444']
        existing_count = Member.objects.count()
        color = colors[existing_count % len(colors)]
        Member.objects.get_or_create(
            username=username,
            defaults={
                'name':     name,
                'role':     'member',
                'color':    color,
                'password': Member.hash_password(password),
                'active':   True,
            }
        )
    return redirect('flat_manager')


@admin_required
@require_POST
def delete_member(request, member_id):
    try:
        member = Member.objects.get(pk=member_id)
        if member.role != 'admin':
            member.delete()
    except Member.DoesNotExist:
        pass
    return redirect('flat_manager')


@admin_required
@require_POST
def update_monthly_share(request):
    try:
        amount   = float(request.POST.get('monthly_share', 8000))
        settings = AppSettings.objects.first()
        if settings:
            settings.monthly_share = amount
            settings.save()
        else:
            AppSettings.objects.create(monthly_share=amount)
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
    try:
        member = Member.objects.get(name=user['name'])
        if member.password == Member.hash_password(old_pass) and new_pass:
            member.password = Member.hash_password(new_pass)
            member.save()
    except Member.DoesNotExist:
        pass
    role = user['role']
    return redirect('dashboard' if role == 'admin' else 'member_dashboard')
