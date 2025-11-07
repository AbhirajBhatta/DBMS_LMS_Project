from django.db import models
from django.contrib.auth.models import User

class Course(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=10)

    def __str__(self):
        return self.name

class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    due_date = models.DateField()
    status = models.CharField(max_length=20, default='Pending')

    def __str__(self):
        return self.title

class Attendance(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    percentage = models.FloatField()

    def __str__(self):
        return f"{self.student.username} - {self.course.code}"

class Grade(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    marks = models.FloatField()

    def __str__(self):
        return f"{self.student.username} - {self.marks}"

class Quiz(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    date = models.DateField()
    max_marks = models.IntegerField()

    def __str__(self):
        return self.title


# Create your models here.
