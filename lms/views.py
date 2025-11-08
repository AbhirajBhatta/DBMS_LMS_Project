from django.shortcuts import render
from .models import Assignment, Attendance, Grade, Quiz

def dashboard(request):
    assignments = Assignment.objects.all()
    attendance = Attendance.objects.all()
    grades = Grade.objects.all()
    quizzes = Quiz.objects.all()

    context = {
        'assignments': assignments,
        'attendance': attendance,
        'grades': grades,
        'quizzes': quizzes,
    }

    return render(request, 'lms/dashboard.html', context)

# Create your views here.
