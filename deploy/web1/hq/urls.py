from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='gilde_board:board')),
    path('admin/', admin.site.urls),
    path('gilde/', include('gilde.urls')),
]
