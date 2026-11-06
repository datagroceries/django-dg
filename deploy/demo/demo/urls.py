from django.urls import include, path

from demo import views

urlpatterns = [
    path('', views.welcome, name='welcome'),
    path('try/', views.try_it, name='try_it'),
    path('gilde/', include('gilde.urls')),
]
