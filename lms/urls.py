from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),            # Public landing page
    path('dashboard/', views.main, name='main'),
    path('signup/', views.signup, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('add_course/', views.add_course, name='add_course'),
    path('class/<int:class_id>/manage/', views.class_manage, name='class_manage'),
    path('class/<int:class_id>/add_student/', views.add_student, name='add_student'),
    path('class/<int:class_id>/upload_csv/', views.upload_students_csv, name='upload_students_csv'),
    path('class/<int:class_id>/', views.class_detail, name='class_detail'),
    path('class/<int:class_id>/attendance/', views.manage_attendance, name='manage_attendance'),
    path('class/<int:class_id>/attendance/history/<int:student_id>/', views.attendance_history_teacher, name='attendance_history_teacher'),
    path('class/<int:class_id>/attendance/history/', views.attendance_history_student, name='attendance_history_student'),
    path('class/<int:class_id>/delete/', views.delete_course, name='delete_course'),
    path('class/<int:class_id>/remove/<int:enrollment_id>/', views.remove_student, name='remove_student'),
    # lms/urls.py
    path('class/<int:class_id>/clear_attendance/<int:student_id>/', views.clear_student_attendance, name='clear_student_attendance'),
    # ASSIGNMENTS
    path('class/<int:class_id>/assignments/add/', views.add_assignment, name='add_assignment'),
    path('class/<int:class_id>/assignments/teacher/', views.class_assignments_teacher, name='class_assignments_teacher'),
    path('class/<int:class_id>/assignments/student/', views.class_assignments_student, name='class_assignments_student'),
    path('assignment/<int:assignment_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('assignment/<int:assignment_id>/submissions/', views.view_submissions, name='view_submissions'),
    path('submission/<int:submission_id>/grade/', views.grade_submission, name='grade_submission'),
    path('assignment/<int:assignment_id>/edit/', views.edit_assignment, name='edit_assignment'),
    path('assignment/<int:assignment_id>/delete/', views.delete_assignment, name='delete_assignment'),

    #QUIZZES
    path('class/<int:class_id>/quizzes/teacher/', views.quizzes_teacher, name='class_quizzes_teacher'),
    path('class/<int:class_id>/quizzes/student/', views.quizzes_student, name='class_quizzes_student'),
    path('class/<int:class_id>/quizzes/add/', views.add_quiz, name='add_quiz'),
    path('quiz/<int:quiz_id>/add_question/', views.add_question, name='add_question'),
    path('quiz/<int:quiz_id>/attempt/', views.attempt_quiz, name='attempt_quiz'),
    path('quiz/<int:quiz_id>/attempts/', views.view_attempts_teacher, name='view_attempts_teacher'),
    path('quiz/<int:quiz_id>/delete/', views.delete_quiz, name='delete_quiz'),

    #RESOURCES
    path('class/<int:class_id>/resources/', views.class_resources, name='class_resources'),
    path('resource/<int:resource_id>/delete/', views.delete_resource, name='delete_resource'),

    #DISCUSSIONS
    path('class/<int:class_id>/discussions/', views.class_discussions, name='class_discussions'),
    path('discussion/<int:discussion_id>/', views.discussion_detail, name='discussion_detail'),
    path('reply/delete/<int:reply_id>/', views.delete_reply, name='delete_reply'),

]   
