from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout
from django.shortcuts import render, redirect, get_object_or_404
from django.db import IntegrityError
from django.contrib import messages
import csv, io
from .models import Classroom, Enrollment, Profile, Resource, Discussion, Assignment

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

@login_required
def add_course(request):
    if request.user.profile.role != 'teacher':
        return redirect('dashboard')

    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        desc = request.POST.get('description')

        try:
            classroom = Classroom.objects.create(
                name=name,
                code=code,
                description=desc,
                teacher=request.user
            )
            messages.success(request, "Course created successfully.")
            return redirect('class_manage', classroom.id)
        except IntegrityError:
            messages.error(request, "A course with that code already exists.")

    return render(request, 'lms/add_course.html')


@login_required
def class_manage(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    enrollments = Enrollment.objects.filter(classroom=classroom).select_related('student__profile')

    return render(request, 'lms/class_manage.html', {
        'classroom': classroom,
        'enrollments': enrollments
    })


@login_required
def add_student(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    reg_no = request.POST.get('reg_no')

    try:
        profile = Profile.objects.get(reg_no=reg_no, role='student')
        student = profile.user
        Enrollment.objects.get_or_create(classroom=classroom, student=student)
        messages.success(request, f"{student.username} added successfully.")
    except Profile.DoesNotExist:
        messages.error(request, "No student found with that register number.")
    except IntegrityError:
        messages.warning(request, "Student already enrolled.")

    return redirect('class_manage', class_id=class_id)


@login_required
def upload_students_csv(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)

    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        if not csv_file.name.endswith('.csv'):
            messages.error(request, "Please upload a valid CSV file.")
            return redirect('class_manage', class_id=class_id)

        data = csv_file.read().decode('utf-8')
        io_string = io.StringIO(data)
        added = 0
        for row in csv.reader(io_string):
            if len(row) < 1:
                continue
            reg_no = row[0].strip()
            try:
                profile = Profile.objects.get(reg_no=reg_no, role='student')
                Enrollment.objects.get_or_create(classroom=classroom, student=profile.user)
                added += 1
            except Profile.DoesNotExist:
                continue
        messages.success(request, f"{added} students added successfully.")

    return redirect('class_manage', class_id=class_id)