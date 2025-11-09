from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# -----------------------------
# PROFILE (extends User)
# -----------------------------
class Profile(models.Model):
    ROLE_CHOICES = (('student', 'Student'), ('teacher', 'Teacher'))
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    reg_no = models.CharField(max_length=30, blank=True, null=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    department = models.CharField(max_length=100, blank=True, null=True)
    year = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


# -----------------------------
# CLASSROOM
# -----------------------------
class Classroom(models.Model):
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='owned_classrooms')
    created_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField(default=timezone.now) 
    def __str__(self):
        return f"{self.code} - {self.name}"


# -----------------------------
# ENROLLMENT
# -----------------------------
class Enrollment(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='enrollments')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'classroom')

    def attendance_percent(self):
        total_classes = self.attendance_records.count()
        if total_classes == 0:
            return 0.0
        attended = self.attendance_records.filter(present=True).count()
        return round((attended / total_classes) * 100, 2)

    def __str__(self):
        return f"{self.student.username} → {self.classroom.code}"


# -----------------------------
# ATTENDANCE
# -----------------------------
class Attendance(models.Model):
    enrollment = models.ForeignKey(
        'Enrollment',
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    date = models.DateField(default=timezone.now)
    present = models.BooleanField(default=False)

    class Meta:
        unique_together = ('enrollment', 'date')

    def __str__(self):
        status = "Present" if self.present else "Absent"
        return f"{self.enrollment.student.username} - {self.enrollment.classroom.code} ({status})"


# -----------------------------
# ASSIGNMENTS & SUBMISSIONS
# -----------------------------
class Assignment(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='assignments')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    visible = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 👇 New field: Teacher’s question file (optional)
    attachment = models.FileField(
        upload_to='assignments/',
        blank=True,
        null=True,
        help_text="Optional PDF or image of the assignment question."
    )

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"

    @property
    def is_active(self):
        return self.deadline >= timezone.now()

    @property
    def is_past_due(self):
        return self.deadline < timezone.now()


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='submissions/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    marks = models.FloatField(blank=True, null=True)
    graded = models.BooleanField(default=False)
    released = models.BooleanField(default=False)

    # ✅ Track resubmissions (each update overwrites file, but timestamp gets stored separately)
    last_resubmitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('assignment', 'student')

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"

    def is_late(self):
        """Return True if the submission was made after the assignment deadline."""
        return self.submitted_at > self.assignment.deadline

    def can_resubmit(self):
        """Check if student is still allowed to resubmit."""
        return timezone.now() <= self.assignment.deadline

    
class SubmissionHistory(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='history')
    timestamp = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=20, default='Submitted')

    def __str__(self):
        return f"{self.submission.student.username} - {self.action} @ {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


# -----------------------------
# QUIZ SYSTEM
# -----------------------------
class Quiz(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    deadline = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    visible = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"

    @property
    def is_active(self):
        return timezone.now() <= self.deadline


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    option_a = models.CharField(max_length=200)
    option_b = models.CharField(max_length=200)
    option_c = models.CharField(max_length=200)
    option_d = models.CharField(max_length=200)
    correct_option = models.CharField(
        max_length=1,
        choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')]
    )

    def __str__(self):
        return f"Q: {self.text[:50]}..."


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.FloatField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)
    graded = models.BooleanField(default=True)  # For integration with overview

    class Meta:
        unique_together = ('quiz', 'student')

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}: {self.score}"


# -----------------------------
# STUDY MATERIALS
# -----------------------------
class Resource(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='resources')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to='resources/', blank=True, null=True)
    link = models.URLField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"


# -----------------------------
# DISCUSSIONS + COMMENTS
# -----------------------------
class Discussion(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='discussions')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"


class Comment(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.author.username}: {self.content[:40]}"
