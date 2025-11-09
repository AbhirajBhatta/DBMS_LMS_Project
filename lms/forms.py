# lms/forms.py
from django import forms
from .models import Assignment

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
