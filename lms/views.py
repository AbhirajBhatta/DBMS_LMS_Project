from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from .models import Classroom, Enrollment

# Main dashboard (replaces old dashboard)
@login_required
def main(request):
    user = request.user

    # Determine user role from profile
    role = user.profile.role if hasattr(user, 'profile') else None

    # Teacher: show classrooms they created
    if role == 'teacher':
        classrooms = Classroom.objects.filter(teacher=user)

    # Student: show classrooms they're enrolled in
    elif role == 'student':
        classrooms = Classroom.objects.filter(enrollments__student=user)

    # Fallback: no role or unassigned profile
    else:
        classrooms = []

    context = {
        'classrooms': classrooms,
        'role': role,
    }

    return render(request, 'lms/dashboard.html', context)


# Optional: simple logout handler
def logout_view(request):
    logout(request)
    return redirect('login')


# Create your views here.

