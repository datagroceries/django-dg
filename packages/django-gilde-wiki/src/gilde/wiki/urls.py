from django.urls import path

from gilde.wiki import views

app_name = 'gilde_wiki'

# The wiki's own pages are under "-/", which no page's address can start with: a slug never starts with
# a dash. A page's address is its path in the tree, so it comes last.
urlpatterns = [
    path('', views.home, name='home'),
    path('-/new/', views.page_create, name='page_create'),
    path('-/arrange/', views.tree_arrange, name='tree_arrange'),
    path('-/files/<int:pk>/<str:name>', views.attachment, name='attachment'),
    path('<path:path>/-/edit/', views.page_edit, name='page_edit'),
    path('<path:path>/-/move/', views.page_move, name='page_move'),
    path('<path:path>/-/delete/', views.page_delete, name='page_delete'),
    path('<path:path>/-/history/', views.page_history, name='page_history'),
    path('<path:path>/-/history/<int:version>/', views.page_compare, name='page_compare'),
    path('<path:path>/-/history/<int:version>/restore/', views.page_restore, name='page_restore'),
    path('<path:path>/-/upload/', views.page_upload, name='page_upload'),
    path('<path:path>/-/attach/', views.page_attach, name='page_attach'),
    path('<path:path>/-/comments/', views.comment_create, name='comment_create'),
    path('<path:path>/-/comments/<int:pk>/', views.comment_edit, name='comment_edit'),
    path('<path:path>/-/watch/', views.page_watch, name='page_watch'),
    path('<path:path>/', views.page, name='page'),
]
