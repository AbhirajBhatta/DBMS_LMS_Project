from django.contrib import admin
from .models import (
    Profile,
    Classroom,
    Enrollment,
    Assignment,
    Submission,
    Attendance,
    Quiz,
    Question,
    QuizAttempt,
    Resource,
    Discussion,
    Comment
)

# Register all models for easy data management in admin panel
admin.site.register(Profile)
admin.site.register(Classroom)
admin.site.register(Enrollment)
admin.site.register(Assignment)
admin.site.register(Submission)
admin.site.register(Attendance)
admin.site.register(Quiz)
admin.site.register(Question)
admin.site.register(QuizAttempt)
admin.site.register(Resource)
admin.site.register(Discussion)
admin.site.register(Comment)



# Register your models here.
