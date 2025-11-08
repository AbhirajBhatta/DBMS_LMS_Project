from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    # path('logout/', views.logout_view, name='logout'),
]
