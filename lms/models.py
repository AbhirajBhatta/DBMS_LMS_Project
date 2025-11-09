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

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"

    @property
    def is_active(self):
        from django.utils import timezone
        return self.deadline >= timezone.now()


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='submissions/', blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    marks = models.FloatField(blank=True, null=True)
    graded = models.BooleanField(default=False)
    released = models.BooleanField(default=False)

    class Meta:
        unique_together = ('assignment', 'student')

    def __str__(self):
        return f"{self.student.username} - {self.assignment.title}"


# -----------------------------
# QUIZ SYSTEM
# -----------------------------
class Quiz(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='quizzes')
    title = models.CharField(max_length=200)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    max_marks = models.IntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    release_grades = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.title} ({self.classroom.code})"


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    marks = models.IntegerField(default=1)

    def __str__(self):
        return f"Q{self.id}: {self.text[:40]}"


class QuizOption(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.text[:50]}"


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0)
    submitted = models.BooleanField(default=False)
    graded = models.BooleanField(default=False)

    class Meta:
        unique_together = ('quiz', 'student')

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}"


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
