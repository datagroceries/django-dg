from django.urls import path

from gilde.wiki import views

app_name = 'gilde_wiki'

# The wiki's own pages are under "-/", which no page's address can start with: a slug never starts with
# a dash. A page's address is its path in the tree, so it comes last.
urlpatterns = [
    path('', views.home, name='home'),
    path('-/new/', views.page_create, name='page_create'),
    path('<path:path>/-/edit/', views.page_edit, name='page_edit'),
    path('<path:path>/-/move/', views.page_move, name='page_move'),
    path('<path:path>/-/delete/', views.page_delete, name='page_delete'),
    path('<path:path>/', views.page, name='page'),
]
