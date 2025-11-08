from django.shortcuts import render
from .models import Course
from django.contrib.auth.decorators import login_required

# Create your views here.
if Users.objects.filter(username=u,password=p).exists():
    return redirect("main")

@login_required
def main(request):
    courses = Course.objects.all()   # later we can filter by user if needed
    return render(request, 'main.html', {'courses': courses})
