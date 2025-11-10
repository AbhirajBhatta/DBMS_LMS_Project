from django.contrib import admin
from .models import (
    Profile,
    Classroom,
    Enrollment,
    Assignment,
    Submission,
    Attendance,
    Option,
    Quiz,
    Question,
    QuizAttempt,
    Resource,
    Discussion,
    Reply
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
admin.site.register(Option)
admin.site.register(QuizAttempt)
admin.site.register(Resource)
admin.site.register(Discussion)
admin.site.register(Reply)



# Register your models here.
