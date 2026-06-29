from django.urls import path
from . import views

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────
    path('login/',                              views.login_view,          name='login'),
    path('logout/',                             views.logout_view,         name='logout'),
    path('change-password/',                    views.change_password,     name='change_password'),

    # ── Admin: personal expenses ──────────────────────────────
    path('',                                    views.dashboard,           name='dashboard'),
    path('add/',                                views.add_expense,         name='add_expense'),
    path('get/<str:expense_id>/',               views.get_expense,         name='get_expense'),
    path('edit/<str:expense_id>/',              views.edit_expense,        name='edit_expense'),
    path('delete/<str:expense_id>/',            views.delete_expense,      name='delete_expense'),
    path('analytics/',                          views.analytics,           name='analytics'),

    # ── Member dashboard ──────────────────────────────────────
    path('member/',                             views.member_dashboard,    name='member_dashboard'),
    path('member/request/',                     views.submit_request,      name='submit_request'),

    # ── Admin: flat manager ───────────────────────────────────
    path('flat/',                               views.flat_manager,        name='flat_manager'),
    path('flat/contribution/add/',              views.add_contribution,    name='add_contribution'),
    path('flat/shared/add/',                    views.add_shared_expense,  name='add_shared_expense'),
    path('flat/shared/delete/<str:expense_id>/', views.delete_shared_expense, name='delete_shared_expense'),
    path('flat/settlement/add/',                views.add_settlement,      name='add_settlement'),
    path('flat/settlement/settle/<str:settlement_id>/', views.mark_settled,  name='mark_settled'),
    path('flat/settlement/delete/<str:settlement_id>/', views.delete_settlement, name='delete_settlement'),
    path('flat/request/review/<str:request_id>/', views.review_request,   name='review_request'),

    # ── Settings ──────────────────────────────────────────────
    path('flat/member/update/<str:member_id>/', views.update_member,       name='update_member'),
    path('flat/share/update/',                  views.update_monthly_share, name='update_monthly_share'),
]
