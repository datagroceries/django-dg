from django.urls import path

from datagroceries.wiki import api, views

app_name = 'dg_wiki'

# The wiki's own pages are under "-/", which no page's address can start with: a slug never starts with
# a dash. A page's address is its path in the tree, so it comes last.
urlpatterns = [
    path('', views.home, name='home'),
    path('-/new/', views.page_create, name='page_create'),
    path('-/search/', views.page_search, name='search'),
    path('-/export/', views.wiki_export, name='wiki_export'),
    path('-/arrange/', views.tree_arrange, name='tree_arrange'),
    path('-/files/<int:pk>/<str:name>', views.attachment, name='attachment'),
    # The REST API (api.py). A page's own parts come after "-/", as on the pages, so no page's address
    # can be taken for one; the page itself comes last.
    path('-/api/pages/', api.PageListCreateView.as_view(), name='api_pages'),
    path('-/api/pages/<path:path>/-/history/', api.PageHistoryView.as_view(), name='api_page_history'),
    path('-/api/pages/<path:path>/-/history/<int:version>/', api.PageVersionView.as_view(), name='api_page_version'),
    path('-/api/pages/<path:path>/-/comments/', api.PageCommentsView.as_view(), name='api_page_comments'),
    path(
        '-/api/pages/<path:path>/-/comments/<int:comment_id>/', api.PageCommentView.as_view(), name='api_page_comment'
    ),
    path('-/api/pages/<path:path>/-/watch/', api.PageWatchView.as_view(), name='api_page_watch'),
    path('-/api/pages/<path:path>/-/translations/', api.PageTranslationsView.as_view(), name='api_page_translations'),
    path('-/api/pages/<path:path>/', api.PageDetailView.as_view(), name='api_page'),
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
    path('<path:path>/-/export/', views.page_export, name='page_export'),
    path('<path:path>/-/translate/', views.page_translate, name='page_translate'),
    path('<path:path>/', views.page, name='page'),
]
