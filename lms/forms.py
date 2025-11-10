# lms/forms.py
from django import forms
from .models import Assignment, Quiz, Discussion, Reply, Profile
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm

class AssignmentForm(forms.ModelForm):
    class Meta:
        model = Assignment
        fields = ['title', 'description', 'deadline', 'attachment']
        widgets = {
            'deadline': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'class': 'form-control bg-dark text-light border-secondary'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control bg-dark text-light border-secondary'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control bg-dark text-light border-secondary',
                'rows': 3
            }),
            'attachment': forms.ClearableFileInput(attrs={
                'class': 'form-control bg-dark text-light border-secondary',
                'accept': '.pdf,.png,.jpg,.jpeg'
            }),
        }

    def clean_attachment(self):
        file = self.cleaned_data.get('attachment')
        if file:
            if not file.name.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
                raise forms.ValidationError("Only PDF or image files are allowed.")
            if file.size > 5 * 1024 * 1024:  # 5 MB limit
                raise forms.ValidationError("File size cannot exceed 5 MB.")
        return file

class QuizForm(forms.ModelForm):
    class Meta:
        model = Quiz
        fields = ["title", "description", "start_time", "end_time", "visible"]
        widgets = {
            "start_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_time": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

class DiscussionForm(forms.ModelForm):
    class Meta:
        model = Discussion
        fields = ['title', 'content']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter topic title'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Start the discussion...'}),
        }

class ReplyForm(forms.ModelForm):
    class Meta:
        model = Reply
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reply...'}),
        }

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control', 'placeholder': 'Enter your email'
    }))
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('teacher', 'Teacher'),
    ]
    role = forms.ChoiceField(choices=ROLE_CHOICES, required=True,
                             widget=forms.Select(attrs={'class': 'form-control'}))
    reg_no = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Register Number (if student)'}),
        label="Register Number"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2', 'role', 'reg_no']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        reg_no = cleaned_data.get('reg_no')

        if role == 'student' and not reg_no:
            raise forms.ValidationError("Register number is required for students.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']  # ✅ Explicitly assign email
        if commit:
            user.save()
            # ✅ Automatically create the profile
            Profile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                reg_no=self.cleaned_data['reg_no'] if self.cleaned_data['role'] == 'student' else None
            )
        return user