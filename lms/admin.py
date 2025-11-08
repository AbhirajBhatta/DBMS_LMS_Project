from django.contrib import admin
from .models import Course, Assignment, Attendance, Grade, Quiz

admin.site.register(Course)
admin.site.register(Assignment)
admin.site.register(Attendance)
admin.site.register(Grade)
admin.site.register(Quiz)


# Register your models here.
