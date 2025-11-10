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
from datetime import timedelta
def default_quiz_end_time():
    return timezone.now() + timedelta(minutes=10)


class Quiz(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(default=default_quiz_end_time)
    allow_multiple_correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    visible = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"

    @property
    def is_active(self):
        now = timezone.now()
        return self.start_time <= now <= self.end_time


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()

    def __str__(self):
        return f"Q: {self.text[:50]}"


class Option(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return self.text


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    score = models.FloatField(default=0)
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded = models.BooleanField(default=True)
    auto_submitted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-submitted_at']  # newest first

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}: {self.score}"

    @staticmethod
    def best_score(quiz, student):
        """Return the best score (highest) for a quiz-student pair."""
        attempts = QuizAttempt.objects.filter(quiz=quiz, student=student)
        return attempts.aggregate(models.Max('score'))['score__max'] or 0



# -----------------------------
# STUDY MATERIALS
# -----------------------------
class Resource(models.Model):
    classroom = models.ForeignKey('Classroom', on_delete=models.CASCADE, related_name='resources')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    file = models.FileField(upload_to='resources/', null=True, blank=True, default=None)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return self.title


# -----------------------------
# DISCUSSIONS + COMMENTS
# -----------------------------
class Discussion(models.Model):
    classroom = models.ForeignKey('Classroom', on_delete=models.CASCADE, related_name='discussions')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} — {self.classroom.name}"


class Reply(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='child_replies')
    created_at = models.DateTimeField(auto_now_add=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.author.username} on {self.discussion.title}"
