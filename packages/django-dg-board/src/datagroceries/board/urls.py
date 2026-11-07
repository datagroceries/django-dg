from django.urls import path

from datagroceries.board import api, views

app_name = 'dg_board'

urlpatterns = [
    path('', views.board, name='board'),
    path('new/', views.ticket_create, name='ticket_create'),
    path('search/', views.ticket_search, name='ticket_search'),
    path('quick-create/', views.ticket_quick_create, name='ticket_quick_create'),
    # Before the group's own page, which would take "new" for a slug.
    path('groups/new/', views.group_create, name='group_create'),
    path('groups/<slug:slug>/', views.group_edit, name='group_edit'),
    path('groups/<slug:slug>/delete/', views.group_delete, name='group_delete'),
    path('attachments/upload/', views.attachment_upload, name='attachment_upload'),
    path('github/webhook/', views.github_webhook, name='github_webhook'),
    path('api/tickets/', api.TicketListCreateView.as_view(), name='api_tickets'),
    path('api/tickets/groups/', api.TicketGroupsView.as_view(), name='api_ticket_groups'),
    path('api/tickets/<str:key>/', api.TicketDetailView.as_view(), name='api_ticket'),
    path('api/tickets/<str:key>/comments/', api.TicketCommentsView.as_view(), name='api_ticket_comments'),
    path(
        'api/tickets/<str:key>/comments/<int:comment_id>/',
        api.TicketCommentView.as_view(),
        name='api_ticket_comment',
    ),
    path('api/tickets/<str:key>/relations/', api.TicketRelationsView.as_view(), name='api_ticket_relations'),
    path('api/tickets/<str:key>/block/', api.TicketBlockView.as_view(), name='api_ticket_block'),
    path('api/tickets/<str:key>/watch/', api.TicketWatchView.as_view(), name='api_ticket_watch'),
    # Without the name: the address of every image uploaded before it had one.
    path('attachments/<int:pk>/', views.attachment, name='attachment'),
    path('attachments/<int:pk>/<str:name>', views.attachment, name='attachment_file'),
    path('<int:pk>/update/', views.ticket_update, name='ticket_update'),
    path('<int:pk>/move/', views.ticket_move, name='ticket_move'),
    path('<int:pk>/reorder/', views.ticket_reorder, name='ticket_reorder'),
    path('<str:key>/peek/', views.ticket_peek, name='ticket_peek'),
    path('<str:key>/', views.ticket_detail, name='ticket_detail'),
]
