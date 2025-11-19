"""Forms used by the core application.

This module defines Django forms for user registration and login, project
creation/editing and membership management. Forms encapsulate both the
input widgets displayed to users and the server‑side validation logic for
their respective models.
"""

from __future__ import annotations

import re

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, validate_email

from .models import DatabaseEntry, Membership, Project, ProjectCallResult


class RegistrationForm(forms.Form):
    """Collects information required to create a new user account.

    The form includes fields for email, full name, phone number, a flag
    indicating whether the account is for an organisation, and password
    confirmation. Password confirmation ensures that users do not
    accidentally mistype their password when creating an account.
    """

    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'you@example.com',
    }))
    full_name = forms.CharField(label='Full Name', max_length=255, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'John Doe',
    }))
    phone = forms.CharField(label='Phone', max_length=11, widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': '09123456789',
    }))
    organization = forms.BooleanField(label='Organization', required=False, widget=forms.CheckboxInput())
    password = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': '••••••••',
    }))
    confirm_password = forms.CharField(label='Confirm Password', widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': '••••••••',
    }))

    def clean_email(self) -> str:
        email = self.cleaned_data['email']
        if User.objects.filter(username=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email

    def clean(self) -> dict[str, any]:  # type: ignore[override]
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if password and confirm and password != confirm:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned_data


class LoginForm(forms.Form):
    """Simple login form requesting email and password."""

    email = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'you@example.com',
    }))
    password = forms.CharField(label='Password', widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': '••••••••',
    }))


class ProjectForm(forms.ModelForm):
    """Form for creating or editing a project.

    ``filled_samples`` is excluded here because it is managed by the system
    and should not be editable from the user interface. Projects do not
    record an owner; instead, a membership record is created for the
    creating user with appropriate permissions.
    """

    sample_upload = forms.FileField(
        label='Excel Sample Workbook',
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'}),
    )
    call_result_upload = forms.FileField(
        label='Call Result Codes (CSV/Excel)',
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.csv,.xlsx,.xls'}),
    )

    class Meta:
        model = Project
        # Use 'types' field instead of singular 'type' to allow multiple entries.
        fields = [
            'name',
            'status',
            'types',
            'start_date',
            'deadline',
            'sample_size',
            'sample_source',
            'sample_upload',
            'call_result_source',
            'call_result_upload',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'types': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Type 1, Type 2, ...'}),
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'deadline': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'sample_size': forms.NumberInput(attrs={'class': 'form-control'}),
            'sample_source': forms.Select(attrs={'class': 'form-select'}),
            'call_result_source': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sample_upload'].required = False
        widget = self.fields['sample_upload'].widget
        widget.attrs.setdefault('class', 'form-control')
        widget.attrs.setdefault('accept', '.xlsx,.xls')
        self.fields['call_result_upload'].required = False
        call_widget = self.fields['call_result_upload'].widget
        call_widget.attrs.setdefault('class', 'form-control')
        call_widget.attrs.setdefault('accept', '.csv,.xlsx,.xls')
        # When editing an existing project (and the form is not bound),
        # surface the stored ``types`` array as a comma-separated string so
        # the dynamic inputs in the template can pre-populate correctly.
        if not self.is_bound:
            instance_types = getattr(self.instance, 'types', None) or []
            if instance_types:
                self.initial['types'] = ', '.join(instance_types)

    def clean(self) -> dict[str, any]:  # type: ignore[override]
        cleaned_data = super().clean()
        sample_source = cleaned_data.get('sample_source')
        uploaded_file = self.files.get('sample_upload') if hasattr(self, 'files') else None
        existing_file = bool(getattr(self.instance, 'sample_upload', None))
        if (
            sample_source == Project.SampleSource.UPLOAD
            and not uploaded_file
            and not existing_file
        ):
            self.add_error('sample_upload', 'Please upload an Excel workbook that includes the required headers.')

        call_result_source = cleaned_data.get('call_result_source')
        call_upload = self.files.get('call_result_upload') if hasattr(self, 'files') else None
        existing_call_file = bool(getattr(self.instance, 'call_result_upload', None))
        has_existing_codes = False
        if getattr(self.instance, 'pk', None):
            has_existing_codes = self.instance.call_results.exists()
        if (
            call_result_source == Project.CallResultSource.CUSTOM
            and not (call_upload or existing_call_file or has_existing_codes)
        ):
            self.add_error(
                'call_result_upload',
                'Please upload a CSV/Excel file with code, label, is_success columns. / لطفاً فایل CSV/اکسل شامل ستون‌های code، label و is_success بارگذاری کنید.',
            )
        return cleaned_data

    def clean_types(self) -> list[str]:
        """Parse the comma-separated types string into a list of trimmed values.

        The ``types`` field is presented as a single text input where users
        can enter multiple project types separated by commas or
        semicolons.  This method splits the input string on commas or
        semicolons, strips whitespace and filters out empty values.
        Returns a list of type strings for storage in the ArrayField.
        """
        raw = self.cleaned_data.get('types', '')
        if isinstance(raw, list):
            # Already parsed (e.g. from initial data)
            return raw
        if not raw:
            return []
        # Split on commas or semicolons
        parts = [p.strip() for p in raw.replace(';', ',').split(',')]
        return [p for p in parts if p]


class ProjectSampleAppendForm(forms.Form):
    """Form used to append additional respondent rows to an active project."""

    workbook = forms.FileField(
        label='Additional Sample Workbook',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'}),
    )

class UserToProjectForm(forms.Form):
    """Form for assigning a user to a project with panel permissions.

    The available panels correspond to the boolean fields on the
    ``Membership`` model.  ``User Management`` and ``Project Management``
    are intentionally omitted here because those permissions are
    determined implicitly by whether the account represents an
    organisation.  The ``is_owner`` checkbox designates the single
    membership that retains access once the project deadline has passed.
    """

    SUGGESTED_TITLES = [
        ('supervision', 'Supervision'),
        ('interviewer', 'Interviewer'),
        ('reviewer', 'Reviewer'),
    ]
    TITLE_CHOICES = [
        ('', '---------'),
        *SUGGESTED_TITLES,
        ('__custom__', 'Other / سایر'),
    ]

    emails = forms.CharField(
        label='User Emails',
        widget=forms.Textarea(
            attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'first@example.com, second@example.com',
            }
        ),
        help_text='Enter one or more email addresses separated by commas or new lines.',
    )
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        label='Project',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    # Membership title input with suggested values and an "Other" option for custom entries.
    title = forms.TypedChoiceField(
        label='Membership Title',
        required=False,
        choices=TITLE_CHOICES,
        coerce=str,
        empty_value='',
        widget=forms.Select(attrs={'class': 'form-select', 'data-behaviour': 'title-choice'})
    )
    title_custom = forms.CharField(
        label='Custom Title',
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'data-behaviour': 'title-custom', 'placeholder': 'Enter custom title'})
    )
    is_owner = forms.BooleanField(
        label='Project Owner',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    # Panel permissions; all default to False.
    database_management = forms.BooleanField(required=False, label='Database Management')
    quota_management = forms.BooleanField(required=False, label='Quota Management')
    collection_management = forms.BooleanField(required=False, label='Collection Management')
    collection_performance = forms.BooleanField(required=False, label='Collection Performance')
    telephone_interviewer = forms.BooleanField(required=False, label='Telephone Interviewer')
    fieldwork_interviewer = forms.BooleanField(required=False, label='Fieldwork Interviewer')
    focus_group_panel = forms.BooleanField(required=False, label='Focus Group Panel')
    qc_management = forms.BooleanField(required=False, label='QC Management')
    qc_performance = forms.BooleanField(required=False, label='QC Performance')
    voice_review = forms.BooleanField(required=False, label='Voice Review')
    callback_qc = forms.BooleanField(required=False, label='Callback QC')
    coding = forms.BooleanField(required=False, label='Coding')
    statistical_health_check = forms.BooleanField(required=False, label='Statistical Health Check')
    tabulation = forms.BooleanField(required=False, label='Tabulation')
    statistics = forms.BooleanField(required=False, label='Statistics')
    funnel_analysis = forms.BooleanField(required=False, label='Funnel Analysis')
    conjoint_analysis = forms.BooleanField(required=False, label='Conjoint Analysis')
    segmentation_analysis = forms.BooleanField(required=False, label='Segmentation Analysis')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adjust initial values when editing memberships so that custom titles
        # populate the auxiliary input while keeping the select on "Other".
        if not self.is_bound:
            initial_title = self.initial.get('title')
            if initial_title:
                initial_title = str(initial_title)
                suggested_map = {label.casefold(): code for code, label in self.SUGGESTED_TITLES}
                code_map = {code: label for code, label in self.SUGGESTED_TITLES}
                if initial_title.casefold() in suggested_map:
                    matched_code = suggested_map[initial_title.casefold()]
                    self.fields['title'].initial = matched_code
                    self.initial['title'] = matched_code
                elif initial_title in code_map:
                    self.fields['title'].initial = initial_title
                    self.initial['title'] = initial_title
                else:
                    self.initial['title_custom'] = initial_title
                    self.fields['title'].initial = '__custom__'
                    self.fields['title_custom'].initial = initial_title
                    self.initial['title'] = '__custom__'

        # Ensure widgets carry consistent CSS classes (particularly after the
        # select is swapped for hidden inputs in edit view contexts).
        self.fields['title'].widget.attrs.setdefault('class', 'form-select')
        self.fields['title_custom'].widget.attrs.setdefault('class', 'form-control')
        self.fields['is_owner'].widget.attrs.setdefault('class', 'form-check-input')
        if 'is_owner' not in self.initial:
            self.initial['is_owner'] = False
        self.fields['is_owner'].initial = self.initial.get('is_owner', False)

    def clean(self) -> dict[str, any]:  # type: ignore[override]
        cleaned_data = super().clean()
        title_choice = (cleaned_data.get('title') or '').strip()
        custom_value = cleaned_data.get('title_custom', '').strip()

        if title_choice == '__custom__':
            if not custom_value:
                self.add_error('title_custom', 'Please provide a custom title.')
            cleaned_data['title'] = custom_value
        elif title_choice:
            label_map = {code: label for code, label in self.SUGGESTED_TITLES}
            cleaned_data['title'] = label_map.get(title_choice, title_choice)
        else:
            cleaned_data['title'] = ''

        # The auxiliary field should not leak into membership kwargs.
        cleaned_data.pop('title_custom', None)
        cleaned_data['is_owner'] = bool(cleaned_data.get('is_owner'))
        return cleaned_data

    def clean_emails(self) -> list[str]:
        """Validate and normalise the submitted email addresses."""

        raw_value = self.cleaned_data.get('emails', '')
        if isinstance(raw_value, list):
            parts = raw_value
        else:
            parts = re.split(r'[\n,]+', str(raw_value))
        emails: list[str] = []
        for part in parts:
            email = part.strip()
            if not email:
                continue
            try:
                validate_email(email)
            except ValidationError as exc:
                raise ValidationError(f'Invalid email: {email}') from exc
            emails.append(email.lower())
        if not emails:
            raise ValidationError('Please provide at least one email address.')
        return emails


class MembershipWorkbookForm(forms.Form):
    """Simple form wrapper around the membership workbook upload."""

    workbook = forms.FileField(
        label='Membership Excel Workbook',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])],
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control',
                'accept': '.xlsx,.xls',
            }
        ),
    )


# Form for creating or editing a database entry (Database Management panel)
class DatabaseEntryForm(forms.ModelForm):
    class Meta:
        model = DatabaseEntry
        fields = ['project', 'db_name', 'token', 'asset_id']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'db_name': forms.TextInput(attrs={'class': 'form-control'}),
            'token': forms.TextInput(attrs={'class': 'form-control'}),
            'asset_id': forms.TextInput(attrs={'class': 'form-control'}),
        }
