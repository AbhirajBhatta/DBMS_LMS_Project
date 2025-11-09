from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout
from django.shortcuts import render, redirect, get_object_or_404
from django.db import IntegrityError
from django.contrib import messages
import csv, io
from django.db.models import Avg
from .models import Classroom, Enrollment, Profile, Resource, Discussion, Assignment, Submission, QuizAttempt, Attendance
from datetime import date, datetime
from django.utils.dateformat import DateFormat
from django.utils import timezone
from django.contrib import messages

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

    # clear old messages
    storage = messages.get_messages(request)
    storage.used = True

    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        desc = request.POST.get('description')
        start_date_str = request.POST.get('start_date')

        start_date = date.today()
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Invalid start date format.")
                return redirect('add_course')

        try:
            classroom = Classroom.objects.create(
                name=name,
                code=code,
                description=desc,
                teacher=request.user,
                start_date=start_date
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


@login_required
def class_detail(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id)
    enrollment = Enrollment.objects.filter(student=request.user, classroom=classroom).first()

    # Compute attendance percentage
    attendance = 0
    if enrollment:
        attendance = enrollment.attendance_percent()

    # Color logic for attendance
    if attendance < 75:
        attendance_color = "danger"
    elif attendance < 80:
        attendance_color = "warning"
    elif attendance < 90:
        attendance_color = "info"
    else:
        attendance_color = "success"

    # ✅ NEW: Dynamic Grade Computation
    assignment_avg = Submission.objects.filter(
        student=request.user,
        assignment__classroom=classroom,
        graded=True,
        released=True
    ).aggregate(Avg('marks'))['marks__avg'] or 0

    quiz_avg = QuizAttempt.objects.filter(
        student=request.user,
        quiz__classroom=classroom,
        graded=True
    ).aggregate(Avg('score'))['score__avg'] or 0

    # Weighted grade (example: 60% assignments, 40% quizzes)
    final_grade = round(0.6 * assignment_avg + 0.4 * quiz_avg, 2)

    context = {
        "classroom": classroom,
        "attendance": attendance,
        "attendance_color": attendance_color,
        "assignment_avg": round(assignment_avg, 2),
        "quiz_avg": round(quiz_avg, 2),
        "final_grade": final_grade,
    }
    return render(request, "lms/class_detail.html", context)


@login_required
def manage_attendance(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    students = Enrollment.objects.filter(classroom=classroom).select_related('student')

    # Selected date from GET (default = today)
    selected_date_str = request.GET.get('date')
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else date.today()

    # Validate date range
    today = date.today()
    if selected_date > today:
        messages.error(request, "You cannot mark attendance for future dates.")
        return redirect(f"/class/{classroom.id}/attendance/?date={today}")
    if selected_date < classroom.start_date:
        messages.error(request, f"You cannot mark attendance before course start date ({classroom.start_date}).")
        return redirect(f"/class/{classroom.id}/attendance/?date={today}")

    # Handle POST (Mark / Clear Attendance)
    if request.method == "POST":
        if "clear_logs" in request.POST:
            Attendance.objects.filter(enrollment__in=students, date=selected_date).delete()
            messages.success(request, f"Attendance logs cleared for {selected_date}.")
            return redirect('manage_attendance', class_id=classroom.id)

        for enrollment in students:
            present_key = f"present_{enrollment.id}"
            present_value = request.POST.get(present_key) == "on"
            Attendance.objects.update_or_create(
                enrollment=enrollment,
                date=selected_date,
                defaults={'present': present_value}
            )
        messages.success(request, f"Attendance saved for {selected_date}.")
        return redirect('manage_attendance', class_id=classroom.id)

    # Attendance map for selected date
    attendance_records = Attendance.objects.filter(enrollment__in=students, date=selected_date)
    attendance_map = {a.enrollment.id: a.present for a in attendance_records}

    return render(request, 'lms/manage_attendance.html', {
        'classroom': classroom,
        'students': students,
        'attendance_map': attendance_map,
        'selected_date': selected_date,
        'today': date.today(),
    })

@login_required
def attendance_history_teacher(request, class_id, student_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    enrollment = get_object_or_404(Enrollment, classroom=classroom, student__id=student_id)
    records = Attendance.objects.filter(enrollment=enrollment).order_by('-date')
    return render(request, 'lms/attendance_history_teacher.html', {
        'classroom': classroom,
        'enrollment': enrollment,
        'records': records,
    })


@login_required
def attendance_history_student(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id)
    enrollment = get_object_or_404(Enrollment, classroom=classroom, student=request.user)
    records = Attendance.objects.filter(enrollment=enrollment).order_by('-date')
    return render(request, 'lms/attendance_history_student.html', {
        'classroom': classroom,
        'records': records,
    })

@login_required
def delete_course(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)

    if request.method == 'POST':
        classroom.delete()
        messages.success(request, "Course deleted successfully.")
        return redirect('main')  # ✅ always redirect to dashboard after deletion

    # If someone opens delete URL directly (GET)
    messages.warning(request, "Please confirm deletion through the course management page.")
    return redirect('class_manage', class_id=class_id)

@login_required
def remove_student(request, class_id, enrollment_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, classroom=classroom)
    if request.method == 'POST':
        # Also delete attendance records
        Attendance.objects.filter(enrollment=enrollment).delete()
        enrollment.delete()
        messages.success(request, f"{enrollment.student.username} removed successfully.")
    return redirect('class_manage', class_id=classroom.id)

@login_required
def clear_student_attendance(request, class_id, student_id):
    """Allows teacher to clear all attendance records for a specific student in their class."""
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    enrollment = get_object_or_404(Enrollment, classroom=classroom, student__id=student_id)

    if request.method == 'POST':
        deleted_count, _ = Attendance.objects.filter(enrollment=enrollment).delete()
        messages.success(request, f"Cleared {deleted_count} attendance logs for {enrollment.student.username}.")
        return redirect('class_manage', class_id=classroom.id)

    messages.warning(request, "Attendance can only be cleared via POST request.")
    return redirect('class_manage', class_id=classroom.id)

from django.core.files.storage import FileSystemStorage

# --------------------------------
# ASSIGNMENTS
# --------------------------------

@login_required
def add_assignment(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)

    if request.method == 'POST':
        title = request.POST.get('title')
        desc = request.POST.get('description')
        deadline = request.POST.get('deadline')

        if not title or not deadline:
            messages.error(request, "Title and deadline are required.")
            return redirect('add_assignment', class_id=classroom.id)

        Assignment.objects.create(
            classroom=classroom,
            title=title,
            description=desc,
            deadline=deadline
        )
        messages.success(request, "Assignment added successfully.")
        return redirect('class_assignments_teacher', class_id=classroom.id)

    return render(request, 'lms/add_assignment.html', {'classroom': classroom})


@login_required
def class_assignments_teacher(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    assignments = classroom.assignments.order_by('-created_at')

    return render(request, 'lms/class_assignments_teacher.html', {
        'classroom': classroom,
        'assignments': assignments
    })


@login_required
def class_assignments_student(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id)
    assignments = classroom.assignments.filter(visible=True).order_by('-created_at')

    # include submission info
    submissions = Submission.objects.filter(student=request.user, assignment__in=assignments)
    submission_map = {s.assignment.id: s for s in submissions}

    return render(request, 'lms/class_assignments_student.html', {
        'classroom': classroom,
        'assignments': assignments,
        'submission_map': submission_map,
        'now': timezone.now(),
    })


@login_required
def submit_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom
    enrollment = Enrollment.objects.filter(student=request.user, classroom=classroom).first()

    if not enrollment:
        messages.error(request, "You are not enrolled in this class.")
        return redirect('main')

    # Prevent submissions after the deadline
    if timezone.now() > assignment.deadline:
        messages.error(request, "The submission deadline has passed.")
        return redirect('class_assignments_student', class_id=classroom.id)

    if request.method == 'POST':
        file = request.FILES.get('file')

        if not file:
            messages.error(request, "Please upload a file before submitting.")
            return redirect('class_assignments_student', class_id=classroom.id)

        # Save or update the submission
        Submission.objects.update_or_create(
            student=request.user,
            assignment=assignment,
            defaults={
                'file': file,
                'submitted_at': timezone.now()
            }
        )

        messages.success(request, f"'{assignment.title}' submitted successfully.")
        return redirect('class_assignments_student', class_id=classroom.id)

    messages.error(request, "Invalid submission request.")
    return redirect('class_assignments_student', class_id=classroom.id)



@login_required
def grade_submission(request, submission_id):
    submission = get_object_or_404(Submission, id=submission_id, assignment__classroom__teacher=request.user)
    
    if request.method == 'POST':
        marks = request.POST.get('marks')
        submission.marks = float(marks)
        submission.graded = True
        submission.released = 'release' in request.POST
        submission.save()
        messages.success(request, f"Marks updated for {submission.student.username}.")
        return redirect('view_submissions', assignment_id=submission.assignment.id)
    
    return render(request, 'lms/grade_submission.html', {'submission': submission})


@login_required
def view_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id, classroom__teacher=request.user)
    submissions = Submission.objects.filter(assignment=assignment).select_related('student')
    return render(request, 'lms/view_submissions.html', {
        'assignment': assignment,
        'submissions': submissions,
    })
