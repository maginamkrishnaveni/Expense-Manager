"""
Django ORM Models — SQLite backend
Replaces all MongoDB pymongo collections with proper Django models.
"""

import hashlib
from django.db import models


# ══════════════════════════════════════════════════════════════
#  MEMBER
# ══════════════════════════════════════════════════════════════

class Member(models.Model):
    ROLE_CHOICES = [('admin', 'Admin'), ('member', 'Member')]

    name       = models.CharField(max_length=100, unique=True)
    username   = models.CharField(max_length=100, unique=True)
    password   = models.CharField(max_length=256)   # sha256 hex
    role       = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    color      = models.CharField(max_length=20, default='#6366f1')
    active     = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @staticmethod
    def hash_password(raw):
        return hashlib.sha256(raw.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════
#  CATEGORY
# ══════════════════════════════════════════════════════════════

class Category(models.Model):
    name  = models.CharField(max_length=100, unique=True)
    icon  = models.CharField(max_length=50, default='bi-three-dots')
    color = models.CharField(max_length=20, default='#E7E9ED')

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


# ══════════════════════════════════════════════════════════════
#  APP SETTINGS  (single-row config table)
# ══════════════════════════════════════════════════════════════

class AppSettings(models.Model):
    currency      = models.CharField(max_length=5,  default='₹')
    currency_code = models.CharField(max_length=10, default='INR')
    app_name      = models.CharField(max_length=100, default='ExpenseIQ')
    monthly_share = models.FloatField(default=8000)

    class Meta:
        verbose_name = 'App Settings'
        verbose_name_plural = 'App Settings'

    def __str__(self):
        return 'App Settings'


# ══════════════════════════════════════════════════════════════
#  PERSONAL EXPENSE  (admin's own expenses)
# ══════════════════════════════════════════════════════════════

class Expense(models.Model):
    title      = models.CharField(max_length=200)
    amount     = models.FloatField()
    category   = models.CharField(max_length=100, default='Other')
    date       = models.DateField()
    note       = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} — ₹{self.amount}'


# ══════════════════════════════════════════════════════════════
#  CONTRIBUTION  (monthly share paid by each member)
# ══════════════════════════════════════════════════════════════

class Contribution(models.Model):
    member     = models.CharField(max_length=100)
    amount     = models.FloatField()
    month      = models.IntegerField()
    year       = models.IntegerField()
    note       = models.TextField(blank=True, default='')
    paid_on    = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-month', 'member']

    def __str__(self):
        return f'{self.member} — ₹{self.amount} ({self.month}/{self.year})'


# ══════════════════════════════════════════════════════════════
#  SHARED EXPENSE  (flat-level expenses)
# ══════════════════════════════════════════════════════════════

class SharedExpense(models.Model):
    title      = models.CharField(max_length=200)
    amount     = models.FloatField()
    category   = models.CharField(max_length=100, default='Other')
    date       = models.DateField()
    paid_by    = models.CharField(max_length=100)
    from_pool  = models.BooleanField(default=True)   # False = paid from own pocket
    note       = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.title} — ₹{self.amount} (paid by {self.paid_by})'


# ══════════════════════════════════════════════════════════════
#  SETTLEMENT  (flatmate spent own money, admin owes them)
# ══════════════════════════════════════════════════════════════

class Settlement(models.Model):
    paid_by     = models.CharField(max_length=100)
    amount      = models.FloatField()
    description = models.CharField(max_length=200)
    date        = models.DateField()
    month       = models.IntegerField()
    year        = models.IntegerField()
    settled     = models.BooleanField(default=False)
    settled_on  = models.DateTimeField(null=True, blank=True)
    note        = models.TextField(blank=True, default='')
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.paid_by} — ₹{self.amount} ({"settled" if self.settled else "pending"})'


# ══════════════════════════════════════════════════════════════
#  REIMBURSEMENT REQUEST  (flatmate requests money from admin)
# ══════════════════════════════════════════════════════════════

class ReimbursementRequest(models.Model):
    STATUS_CHOICES = [
        ('pending',  'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    requested_by = models.CharField(max_length=100)
    amount       = models.FloatField()
    description  = models.CharField(max_length=200)
    date         = models.DateField()
    month        = models.IntegerField()
    year         = models.IntegerField()
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_note   = models.TextField(blank=True, default='')
    reviewed_on  = models.DateTimeField(null=True, blank=True)
    note         = models.TextField(blank=True, default='')
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.requested_by} — ₹{self.amount} ({self.status})'
