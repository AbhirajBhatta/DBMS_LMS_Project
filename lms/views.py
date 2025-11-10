from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth import logout
from django.shortcuts import render, redirect, get_object_or_404
from django.db import IntegrityError
from django.contrib import messages
import csv, io
from django.db.models import Max, Avg
from .models import Classroom, Enrollment, Profile, Resource, Discussion, Assignment, Submission, Quiz, Question, Attendance, SubmissionHistory, QuizAttempt, Option
from datetime import date, datetime
from django.utils.dateformat import DateFormat
from django.utils import timezone
from django.contrib import messages
from .forms import AssignmentForm
from django.utils.dateparse import parse_datetime


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

    # === AUTO-MARK / CLEANUP LOGIC (Assignments) ===
    if not is_teacher and enrollment:
        student = request.user
        for a in assignments:
            sub = Submission.objects.filter(student=student, assignment=a).first()

            # If deadline extended -> remove old auto-zero
            if sub and sub.marks == 0 and sub.graded and a.deadline > now:
                sub.delete()
                continue

            # If deadline passed and no submission -> auto-zero
            if not sub and a.deadline < now:
                Submission.objects.update_or_create(
                    student=student,
                    assignment=a,
                    defaults={
                        'marks': 0.0,
                        'graded': True,
                        'released': True,
                        'submitted_at': a.deadline
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

    # === QUIZ LOGIC: Auto-zero, best-of-two, best-score contribution ===
    best_quiz_score = 0
    pending_quiz_exists = False
    quizzes_context = []

    if not is_teacher and enrollment:
        student = request.user
        quizzes = Quiz.objects.filter(classroom=classroom, visible=True).order_by('end_time')

        for quiz in quizzes:
            attempts = QuizAttempt.objects.filter(student=student, quiz=quiz)

            # Clean old auto-zero if quiz extended
            auto_zero = attempts.filter(auto_submitted=True).first()
            if auto_zero and quiz.end_time > now:
                auto_zero.delete()
                attempts = QuizAttempt.objects.filter(student=student, quiz=quiz)

            # Auto-mark 0 if missed and quiz ended
            if not attempts.exists() and quiz.end_time < now:
                QuizAttempt.objects.create(
                    student=student,
                    quiz=quiz,
                    score=0.0,
                    graded=True,
                    auto_submitted=True,
                    submitted_at=quiz.end_time
                )
                attempts = QuizAttempt.objects.filter(student=student, quiz=quiz)

            # Determine quiz status for display
            if quiz.end_time > now and not attempts.exists():
                status = "Quiz Due"
                pending_quiz_exists = True
            elif attempts.exists():
                latest_attempt = attempts.order_by('-submitted_at').first()
                status = f"Attempted • {latest_attempt.score}/10"
            else:
                status = "No Attempts"

            quizzes_context.append({
                "title": quiz.title,
                "status": status
            })

        # --- Best-of logic: find best score per quiz and then the highest across quizzes ---
        all_best_scores = []
        for quiz in Quiz.objects.filter(classroom=classroom, visible=True):
            score = QuizAttempt.best_score(quiz, student)
            if score is not None:
                all_best_scores.append(score)

        if all_best_scores:
            best_quiz_score = max(all_best_scores)
        else:
            best_quiz_score = 0

    # === Assignment Average ===
    assignment_avg = 0
    total_assignments = assignments.count()

    if not is_teacher and total_assignments > 0:
        subs = Submission.objects.filter(student=request.user, assignment__classroom=classroom)
        total_marks = sum(s.marks or 0 for s in subs)
        assignment_avg = round(total_marks / total_assignments, 2)

    # === Final Weighted Grade ===
    # Assignments = 50%, Best Quiz = 50%
    final_grade = round(0.5 * assignment_avg + 0.5 * best_quiz_score, 2)

    # === Overdue Auto-Zero Assignments ===
    overdue_zeros = 0
    if not is_teacher:
        overdue_zeros = Submission.objects.filter(
            student=request.user,
            assignment__classroom=classroom,
            marks=0,
            graded=True,
            assignment__deadline__lt=now
        ).count()

    # === Context ===
    # NOTE: quiz_avg is provided for template compatibility and is the score used for grading (best_quiz_score)
    materials = Resource.objects.filter(classroom=classroom).order_by('-uploaded_at')[:3]
    context = {
        "classroom": classroom,
        "assignments": assignments,
        "attendance": round(attendance, 2),
        "attendance_color": attendance_color,
        "assignment_avg": assignment_avg,
        "quiz_avg": round(best_quiz_score, 2),   # <-- ensures template {{ quiz_avg }} is populated
        "best_quiz_score": round(best_quiz_score, 2),
        "final_grade": final_grade,
        "pending_assignments": pending_assignments,
        "submission_map": submission_map,
        "pending_quiz_exists": pending_quiz_exists,
        "is_teacher": is_teacher,
        "now": now,
        "overdue_zeros": overdue_zeros,
        "quizzes": quizzes_context,  # for template loop
        "materials": materials,
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

#Quizzes

# =========================
# TEACHER: VIEW QUIZZES
# =========================
@login_required
@login_required
def quizzes_teacher(request, class_id):
    """
    Display all quizzes created by the teacher for a given classroom.
    Shows real-time status (Upcoming, Ongoing, Finished) with timezone-safe logic.
    """
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)
    quizzes = list(Quiz.objects.filter(classroom=classroom).order_by('-start_time'))
    now = timezone.now()
    tz = timezone.get_current_timezone()

    for q in quizzes:
        # Normalize start/end times to aware datetimes
        start = q.start_time
        end = q.end_time

        if start and timezone.is_naive(start):
            start = timezone.make_aware(start, tz)
        if end and timezone.is_naive(end):
            end = timezone.make_aware(end, tz)

        # Compute status robustly
        if start and end:
            if start <= now <= end:
                q.status_display = "Ongoing"
                q.status_color = "text-success"
            elif end < now:
                q.status_display = "Finished"
                q.status_color = "text-secondary"
            else:
                q.status_display = "Upcoming"
                q.status_color = "text-warning"
        else:
            q.status_display = "Draft"
            q.status_color = "text-muted"

        # Localize times for display
        q.start_local = timezone.localtime(start) if start else None
        q.end_local = timezone.localtime(end) if end else None

    context = {
        'classroom': classroom,
        'quizzes': quizzes,
        'now': timezone.localtime(now),
    }
    return render(request, 'lms/quizzes_teacher.html', context)


# =========================
# TEACHER: ADD QUIZ
# =========================
@login_required
def add_quiz(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id, teacher=request.user)

    if request.method == 'POST':
        title = request.POST['title'].strip()
        desc = request.POST.get('description', '').strip()
        start = request.POST.get('start_time')
        end = request.POST.get('end_time')
        allow_multiple = bool(request.POST.get('allow_multiple'))

        # prevent duplicate quiz creation
        existing = Quiz.objects.filter(
            classroom=classroom,
            title=title,
            start_time=start,
            end_time=end
        ).first()

        if existing:
            messages.info(request, "Quiz already exists — redirecting to question page.")
            return redirect('add_question', quiz_id=existing.id)

        quiz = Quiz.objects.create(
            classroom=classroom,
            title=title,
            description=desc,
            start_time=start,
            end_time=end,
            allow_multiple_correct=allow_multiple,
            visible=False,
        )

        messages.success(request, "Quiz created successfully.")
        return redirect('add_question', quiz_id=quiz.id)

    return render(request, 'lms/add_quiz.html', {'classroom': classroom})

@login_required
def delete_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, classroom__teacher=request.user)
    title = quiz.title
    quiz.delete()
    messages.success(request, f"Quiz '{title}' deleted successfully.")
    return redirect('class_quizzes_teacher', class_id=quiz.classroom.id)


# =========================
# TEACHER: ADD QUESTIONS
# =========================
@login_required
def add_question(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, classroom__teacher=request.user)
    questions = quiz.questions.prefetch_related('options')

    if request.method == 'POST':
        # 1️⃣ Update Quiz Timings
        if 'update_timing' in request.POST:
            start = request.POST.get('start_time')
            end = request.POST.get('end_time')

            if not start or not end:
                messages.error(request, "Both start and end times are required.")
            else:
                start_dt = parse_datetime(start)
                end_dt = parse_datetime(end)

                if not start_dt or not end_dt:
                    messages.error(request, "Invalid date/time format.")
                elif end_dt <= start_dt:
                    messages.error(request, "End time must be later than start time.")
                else:
                    quiz.start_time = start_dt
                    quiz.end_time = end_dt
                    quiz.save()
                    messages.success(request, "Quiz timings updated successfully.")

            return render(request, 'lms/add_question.html', {'quiz': quiz, 'questions': questions})

        # 2️⃣ Add Question
        elif 'add_question' in request.POST:
            text = request.POST.get('question', '').strip()
            options = request.POST.getlist('option_text')
            correct = request.POST.getlist('correct_option')

            # Backend validation
            if not text:
                messages.error(request, "Question text cannot be empty.")
            elif len(options) < 2:
                messages.error(request, "Please provide at least two options.")
            elif not correct:
                messages.error(request, "Please select at least one correct answer.")
            else:
                # Create question + options
                q = Question.objects.create(quiz=quiz, text=text)
                for i, opt in enumerate(options):
                    Option.objects.create(
                        question=q,
                        text=opt.strip(),
                        is_correct=(str(i) in correct)
                    )
                quiz.visible = True
                quiz.save()
                messages.success(request, "Question added successfully.")

            questions = quiz.questions.prefetch_related('options')
            return render(request, 'lms/add_question.html', {'quiz': quiz, 'questions': questions})

        # 3️⃣ Save Quiz
        elif 'save_quiz' in request.POST:
            if quiz.questions.count() == 0:
                messages.error(request, "Quiz must have at least one question before saving.")
            elif not quiz.start_time or not quiz.end_time:
                messages.error(request, "Please set valid start and end times before saving.")
            elif quiz.end_time <= quiz.start_time:
                messages.error(request, "End time must be later than start time.")
            else:
                messages.success(request, "Quiz saved successfully.")
                return redirect('class_manage', class_id=quiz.classroom.id)

            return render(request, 'lms/add_question.html', {'quiz': quiz, 'questions': questions})

    return render(request, 'lms/add_question.html', {'quiz': quiz, 'questions': questions})



# =========================
# STUDENT: VIEW QUIZZES
# =========================
@login_required
def quizzes_student(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id)

    # Remove 'visible=True' unless you’re explicitly managing it from teacher panel
    quizzes = Quiz.objects.filter(classroom=classroom, visible=True).order_by('start_time')

    now = timezone.localtime(timezone.now())
    attempts = QuizAttempt.objects.filter(student=request.user, quiz__in=quizzes)
    attempt_map = {a.quiz.id: a for a in attempts}

    return render(request, 'lms/quizzes_student.html', {
        'classroom': classroom,
        'quizzes': quizzes,
        'attempt_map': attempt_map,
        'now': now
    })



# =========================
# STUDENT: ATTEMPT QUIZ
# =========================
@login_required
def attempt_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    now = timezone.localtime(timezone.now())

    # Restrict to quiz window
    if now < quiz.start_time:
        messages.error(request, "Quiz hasn’t started yet.")
        return redirect('quizzes_student', class_id=quiz.classroom.id)

    if now > quiz.end_time:
        messages.error(request, "Quiz deadline has passed.")
        QuizAttempt.objects.get_or_create(
            quiz=quiz,
            student=request.user,
            defaults={'score': 0.0, 'graded': True, 'auto_submitted': True}
        )
        return redirect('quizzes_student', class_id=quiz.classroom.id)

    # Handle submission
    if request.method == 'POST':
        questions = quiz.questions.prefetch_related('options')
        total_q = len(questions)
        score = 0

        for q in questions:
            submitted = request.POST.getlist(str(q.id))
            correct = list(q.options.filter(is_correct=True).values_list('id', flat=True))
            if set(map(int, submitted)) == set(correct):
                score += 1

        final_score = round((score / total_q) * 10, 2)
        QuizAttempt.objects.update_or_create(
            quiz=quiz,
            student=request.user,
            defaults={'score': final_score, 'graded': True}
        )

        messages.success(request, f"Quiz submitted successfully! You scored {final_score}/10.")
        return redirect('class_quizzes_student', class_id=quiz.classroom.id)


    questions = quiz.questions.prefetch_related('options')
    return render(request, 'lms/attempt_quiz.html', {
        'quiz': quiz,
        'questions': questions
    })


# =========================
# TEACHER: VIEW ATTEMPTS
# =========================
@login_required
def view_attempts_teacher(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, classroom__teacher=request.user)
    attempts = QuizAttempt.objects.filter(quiz=quiz).select_related('student__profile')

    if request.method == 'POST':
        # Update marks
        if 'update_scores' in request.POST:
            for attempt in attempts:
                marks = request.POST.get(f'score_{attempt.id}')
                if marks:
                    attempt.score = float(marks)
                    attempt.save()
            messages.success(request, "Scores updated successfully.")
            return redirect('view_attempts_teacher', quiz_id=quiz.id)

        # Reactivate attempt
        elif 'reactivate_attempt' in request.POST:
            attempt_id = request.POST.get('attempt_id')
            attempt = get_object_or_404(QuizAttempt, id=attempt_id, quiz=quiz)
            attempt.delete()
  # 👈 Remove previous attempt entirely
            messages.success(request, f"Reactivated quiz for {attempt.student.username}. They can attempt again.")
            return redirect('view_attempts_teacher', quiz_id=quiz.id)

    return render(request, 'lms/view_attempts_teacher.html', {'quiz': quiz, 'attempts': attempts})



#------------------------
#CLASS RESOURCES
#------------------------

@login_required
def class_resources(request, class_id):
    classroom = get_object_or_404(Classroom, id=class_id)
    is_teacher = classroom.teacher == request.user

    resources = Resource.objects.filter(classroom=classroom)

    if request.method == 'POST' and is_teacher:
        title = request.POST.get('title')
        description = request.POST.get('description')
        file = request.FILES.get('file')

        if not title or not file:
            messages.error(request, "Title and file are required.")
        else:
            Resource.objects.create(
                classroom=classroom,
                title=title,
                description=description,
                file=file,
                uploaded_by=request.user
            )
            messages.success(request, "Resource added successfully.")
            return redirect('class_resources', class_id=classroom.id)

    return render(request, 'lms/class_resources.html', {
        'classroom': classroom,
        'resources': resources,
        'is_teacher': is_teacher
    })


@login_required
def delete_resource(request, resource_id):
    resource = get_object_or_404(Resource, id=resource_id)
    classroom = resource.classroom
    if request.user == classroom.teacher:
        resource.delete()
        messages.success(request, "Resource deleted successfully.")
    else:
        messages.error(request, "You are not authorized to delete this resource.")
    return redirect('class_resources', class_id=classroom.id)


