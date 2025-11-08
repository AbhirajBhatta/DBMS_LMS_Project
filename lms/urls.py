from django.urls import path
from . import views

urlpatterns = [
    path('', views.main, name='main'),
    path('add_course/', views.add_course, name='add_course'),
    path('class/<int:class_id>/manage/', views.class_manage, name='class_manage'),
    path('class/<int:class_id>/add_student/', views.add_student, name='add_student'),
    path('class/<int:class_id>/upload_csv/', views.upload_students_csv, name='upload_students_csv'),
    
]
