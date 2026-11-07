"""Mounted by datagroceries.urls at `connect/`. Two namespaces side by side, not one inside the other: the page's
own, `dg_connect`, and the OAuth endpoints', `oauth2_provider`, by which the toolkit finds them."""

from django.urls import include, path

from datagroceries.connect import views

pages = (
    [
        path('', views.connect, name='connect'),
        path('tokens/new/', views.token_create, name='token_create'),
        path('tokens/<int:token_id>/revoke/', views.token_revoke, name='token_revoke'),
        path('apps/<int:application_id>/revoke/', views.connection_revoke, name='connection_revoke'),
    ],
    'dg_connect',
)

urlpatterns = [
    path('', include(pages)),
    path('', include('datagroceries.connect.oauth')),
]
