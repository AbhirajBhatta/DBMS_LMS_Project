from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout
from django.shortcuts import render, redirect, get_object_or_404
from django.db import IntegrityError
from django.contrib import messages
import csv, io
from django.db.models import Avg
from .models import Classroom, Enrollment, Profile, Resource, Discussion, Assignment, Submission, QuizAttempt, Attendance, SubmissionHistory
from datetime import date, datetime
from django.utils.dateformat import DateFormat
from django.utils import timezone
from django.contrib import messages
from .forms import AssignmentForm


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
    is_teacher = classroom.teacher == request.user
    now = timezone.localtime(timezone.now())  # localized to IST

    # === Enrollment for Attendance ===
    enrollment = None
    if not is_teacher:
        enrollment = Enrollment.objects.filter(student=request.user, classroom=classroom).first()

    # === Fetch Visible Assignments ===
    assignments = Assignment.objects.filter(classroom=classroom, visible=True).order_by('deadline')

    # === AUTO-MARK / CLEANUP LOGIC ===
    if not is_teacher and enrollment:
        student = request.user
        for a in assignments:
            sub = Submission.objects.filter(student=student, assignment=a).first()

            # If deadline was extended (now in future), remove prior auto-zero
            if sub and sub.marks == 0 and sub.graded and a.deadline > now:
                sub.delete()
                continue

            # If not submitted and deadline passed → auto-create 0
            if not sub and a.deadline < now:
                Submission.objects.update_or_create(
                    student=student,
                    assignment=a,
                    defaults={
                        'marks': 0.0,
                        'graded': True,
                        'released': True,
                        'submitted_at': a.deadline  # record original deadline as submission time
                    }
                )

    # === Build Submission Map for Template Lookup ===
    submission_map = {}
    if not is_teacher:
        submissions = Submission.objects.filter(student=request.user, assignment__in=assignments)
        submission_map = {s.assignment.id: s for s in submissions}

    # === Pending Assignments Count ===
    pending_assignments = 0
    if not is_teacher:
        for a in assignments:
            sub = submission_map.get(a.id)
            if not sub and a.deadline > now:
                pending_assignments += 1

    # === Attendance Calculation ===
    attendance = 0
    attendance_color = "success"
    if enrollment:
        try:
            attendance = enrollment.attendance_percent()
        except Exception:
            attendance = 0

        if attendance < 75:
            attendance_color = "danger"
        elif attendance < 80:
            attendance_color = "warning"
        elif attendance < 90:
            attendance_color = "info"
        else:
            attendance_color = "success"

    # === Assignment Average (all assignments, including auto-zeros) ===
    assignment_avg = 0
    total_assignments = assignments.count()

    if not is_teacher and total_assignments > 0:
        subs = Submission.objects.filter(student=request.user, assignment__classroom=classroom)
        total_marks = sum(s.marks or 0 for s in subs)
        assignment_avg = round(total_marks / total_assignments, 2)

    # === Quiz Average (if you have quizzes model, else stays 0) ===
    quiz_avg = QuizAttempt.objects.filter(
        student=request.user,
        quiz__classroom=classroom,
        graded=True
    ).aggregate(Avg('score'))['score__avg'] or 0

    # === Final Weighted Grade (Assignments + Quizzes) ===
    final_grade = round(0.5 * assignment_avg + 0.5 * quiz_avg, 2)

    # === Count Overdue Auto-Zero Submissions (for dashboard + per-assignment flag) ===
    overdue_zeros = 0
    if not is_teacher:
        overdue_zeros = Submission.objects.filter(
            student=request.user,
            assignment__classroom=classroom,
            marks=0,
            graded=True,
            assignment__deadline__lt=now
        ).count()

    # === Context for Template ===
    context = {
        "classroom": classroom,
        "assignments": assignments,
        "attendance": round(attendance, 2),
        "attendance_color": attendance_color,
        "assignment_avg": assignment_avg,
        "quiz_avg": round(quiz_avg, 2),
        "final_grade": final_grade,
        "pending_assignments": pending_assignments,
        "submission_map": submission_map,
        "is_teacher": is_teacher,
        "now": now,
        "overdue_zeros": overdue_zeros,
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

# Teacher: Add Assignment
@login_required
def add_assignment(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id)

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.classroom = classroom
            assignment.save()
            messages.success(request, '✅ Assignment added successfully.')
            return redirect('class_assignments_teacher', class_id=classroom.id)
        else:
            messages.error(request, '⚠️ Please correct the errors below.')
    else:
        form = AssignmentForm()

    return render(request, 'lms/add_assignment.html', {
        'form': form,
        'classroom': classroom
    })


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
    enroll = Enrollment.objects.filter(student=request.user, classroom=classroom).first()
    if not enroll:
        messages.error(request, "You are not enrolled in this class.")
        return redirect('main')

    assignments = Assignment.objects.filter(classroom=classroom).order_by('-deadline')
    submissions = Submission.objects.filter(student=request.user, assignment__in=assignments)
    submission_map = {s.assignment.id: s for s in submissions}

    context = {
        'classroom': classroom,
        'assignments': assignments,
        'submissions': submission_map,
        'now': timezone.now(),
    }
    return render(request, 'lms/class_assignments_student.html', context)



@login_required
def submit_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom

    # Ensure the student is enrolled
    enrollment = Enrollment.objects.filter(student=request.user, classroom=classroom).first()
    if not enrollment:
        messages.error(request, "You are not enrolled in this class.")
        return redirect('main')

    # Block submissions after deadline
    if timezone.now() > assignment.deadline:
        messages.error(request, "⛔ Deadline has passed. Submissions are closed.")
        return redirect('class_assignments_student', class_id=classroom.id)

    # Only allow POST requests with a file
    if request.method != 'POST' or 'file' not in request.FILES:
        messages.error(request, "⚠️ Invalid submission request.")
        return redirect('class_assignments_student', class_id=classroom.id)

    file = request.FILES['file']

    # File validation
    if not file.name.lower().endswith('.pdf'):
        messages.error(request, "❌ Only PDF files are allowed.")
        return redirect('class_assignments_student', class_id=classroom.id)

    if file.size > 5 * 1024 * 1024:  # 5 MB
        messages.error(request, "❌ File size cannot exceed 5 MB.")
        return redirect('class_assignments_student', class_id=classroom.id)

    # Save or update submission
    submission, created = Submission.objects.update_or_create(
        student=request.user,
        assignment=assignment,
        defaults={
            'file': file,
            'submitted_at': timezone.now(),
        }
    )

    # Track submission history
    SubmissionHistory.objects.create(submission=submission, action='Resubmitted')


    # Display feedback message
    if created:
        SubmissionHistory.objects.create(submission=submission, action='First Submission')
        messages.success(request, "Assignment submitted successfully.")
    else:
        SubmissionHistory.objects.create(submission=submission, action='Resubmission')
        messages.success(request, "Resubmitted successfully (previous file replaced).")


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


login_required
def view_submissions(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom
    if classroom.teacher != request.user:
        messages.error(request, "You are not authorized to view this page.")
        return redirect('main')

    submissions = Submission.objects.filter(assignment=assignment).select_related('student').prefetch_related('history')

    context = {
        "assignment": assignment,
        "submissions": submissions,
    }
    return render(request, "lms/view_submissions.html", context)

# Teacher: Edit Assignment
@login_required
def edit_assignment(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    classroom = assignment.classroom

    if request.method == 'POST':
        form = AssignmentForm(request.POST, request.FILES, instance=assignment)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Assignment updated successfully.')
            return redirect('class_assignments_teacher', class_id=classroom.id)
        else:
            messages.error(request, '⚠️ Please correct the errors below.')
    else:
        form = AssignmentForm(instance=assignment)

    return render(request, 'lms/edit_assignment.html', {
        'form': form,
        'assignment': assignment,
        'classroom': classroom
    })


