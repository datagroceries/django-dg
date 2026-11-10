from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def start(request):
    """The board for the team; the wiki, with its public folders, for everyone else."""
    return redirect('dg_board:board' if request.user.has_perm('dg_board.use') else 'dg_wiki:home')


urlpatterns = [
    path('', start),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('dg/', include('datagroceries.urls')),
]
