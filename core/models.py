"""Data models for the InsightZen application.

This module defines the database schema for the application using Django's
ORM. The models here reflect the latest specifications provided by the
user, including a more expressive membership model, a rich person
registry with associated mobile numbers, a table for interviews and a
quota table used by the quota management panel.  Project ownership and
panel permissions are governed via the ``Membership`` model where a
single membership per project is flagged as the owner.
"""

from __future__ import annotations

from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField  # type: ignore
from django.utils import timezone


class Notification(models.Model):
    """Stores user facing notifications triggered by application events."""

    class EventType(models.TextChoices):
        MEMBERSHIP_ADDED = 'membership_added', 'Membership Added'
        PROJECT_STARTED = 'project_started', 'Project Started'
        PROJECT_DEADLINE = 'project_deadline', 'Project Deadline'
        CUSTOM_MESSAGE = 'custom_message', 'Custom Message'
        EVENT_INVITE = 'event_invite', 'Event Invitation'
        EVENT_UPDATE = 'event_update', 'Event Updated'
        EVENT_REMINDER = 'event_reminder', 'Event Reminder'

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    project = models.ForeignKey(
        'Project',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='notifications',
    )
    message = models.TextField()
    event_type = models.CharField(max_length=50, choices=EventType.choices)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:  # pragma: no cover
        return f"Notification<{self.recipient.username} {self.event_type}>"


class Profile(models.Model):
    """Additional information associated with a Django auth User.

    The built‑in ``User`` model handles core authentication details such
    as username (we use the email as username), password and names. This
    ``Profile`` model augments it with fields specific to the InsightZen
    application, such as whether the account represents an organisation,
    phone number and the date of registration.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.BooleanField(default=False)
    phone = models.CharField(max_length=11)
    register_date = models.DateField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"Profile of {self.user.username}"


class Person(models.Model):
    """Represents an individual respondent."""

    class GenderChoices(models.TextChoices):
        MALE = 'male', 'Male'
        FEMALE = 'female', 'Female'

    national_code = models.CharField(max_length=10, primary_key=True)
    full_name = models.CharField(max_length=145, blank=True, null=True)
    birth_year = models.IntegerField()
    city_name = models.CharField(max_length=64)
    gender = models.CharField(
        max_length=10,
        choices=GenderChoices.choices,
        blank=True,
        null=True,
    )

    def __str__(self) -> str:  # pragma: no cover
        return self.full_name or self.national_code


class Mobile(models.Model):
    """Stores one or more mobile numbers per person.

    Although the original specification described the mobile number as an
    integer, we store it as a character field to allow for leading zeros
    and non‑numeric characters (e.g. international prefixes) if
    necessary.  Each mobile record is linked to a ``Person`` via a
    foreign key.
    """

    mobile = models.CharField(max_length=15, primary_key=True)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='mobiles')

    def __str__(self) -> str:  # pragma: no cover
        return self.mobile


class ActivityLog(models.Model):
    """Tracks user actions within the application.

    Each log entry records the user who performed the action, a short
    description of the action, optional details and the timestamp.  Logs
    are intended primarily for debugging and auditing purposes and can be
    viewed by organisation administrators from the web interface.
    """

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} - {self.user}: {self.action}"


class Project(models.Model):
    """Represents a research project.

    Ownership is inferred from related ``Membership`` rows with
    ``is_owner`` set to ``True``.  The ``filled_samples`` field tracks the
    number of completed interviews and is automatically initialised to
    zero.  Projects can also declare how their telephone sample pool
    should be sourced: either from the default respondent bank or from a
    user uploaded Excel workbook.  When the upload workflow is enabled
    the associated metadata captures when the file was last processed and
    how many rows were accepted.
    """

    class SampleSource(models.TextChoices):
        DATABASE = 'database', 'Respondent Bank'
        UPLOAD = 'upload', 'Excel Upload'

    class CallResultSource(models.TextChoices):
        DEFAULT = 'default', 'Default Call Codes'
        CUSTOM = 'custom', 'Custom Upload'

    name = models.CharField(max_length=255)
    status = models.BooleanField(default=False)
    # One or more project types stored as an array of strings.  Using
    # ArrayField allows multiple type values to be stored without
    # creating a separate model.  Requires PostgreSQL backend.
    types = ArrayField(models.CharField(max_length=100), blank=True, default=list)
    start_date = models.DateField()
    deadline = models.DateField()
    sample_size = models.PositiveIntegerField()
    filled_samples = models.PositiveIntegerField(default=0)
    sample_source = models.CharField(
        max_length=20,
        choices=SampleSource.choices,
        default=SampleSource.DATABASE,
    )
    sample_upload = models.FileField(
        upload_to='project_samples/',
        null=True,
        blank=True,
    )
    sample_upload_refreshed_at = models.DateTimeField(null=True, blank=True)
    sample_upload_metadata = models.JSONField(default=dict, blank=True)
    call_result_source = models.CharField(
        max_length=20,
        choices=CallResultSource.choices,
        default=CallResultSource.DEFAULT,
    )
    call_result_upload = models.FileField(
        upload_to='project_call_results/',
        null=True,
        blank=True,
    )
    call_result_refreshed_at = models.DateTimeField(null=True, blank=True)
    call_result_metadata = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class ProjectCallResult(models.Model):
    """Stores custom call result codes for a project."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='call_results',
    )
    code = models.IntegerField()
    label = models.CharField(max_length=255)
    is_success = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('project', 'code')
        ordering = ['display_order', 'code']

    def __str__(self) -> str:  # pragma: no cover
        return f"CallResult<{self.project_id}:{self.code}>"


class Membership(models.Model):
    """Associates a user with a project and records panel permissions.

    Each membership record indicates which panels a user may access for
    a given project.  The ``start_work`` date captures when the
    association was created.  Exactly one membership per project should
    have ``is_owner`` set to ``True`` so that, after a project's
    deadline, only the owner retains panel access.  Panel names are
    stored as boolean flags
    corresponding to the list provided by the user, omitting the
    ``User Management`` and ``Project Management`` panels which are
    reserved for organisation administrators.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    start_work = models.DateField(auto_now_add=True)
    # Optional title to describe this membership (e.g. role or label).
    title = models.CharField(max_length=100, blank=True, null=True)
    # Whether this membership represents the designated project owner.
    is_owner = models.BooleanField(default=False)
    # Panel permissions
    database_management = models.BooleanField(default=False)
    quota_management = models.BooleanField(default=False)
    collection_management = models.BooleanField(default=False)
    collection_performance = models.BooleanField(default=False)
    telephone_interviewer = models.BooleanField(default=False)
    fieldwork_interviewer = models.BooleanField(default=False)
    focus_group_panel = models.BooleanField(default=False)
    qc_management = models.BooleanField(default=False)
    qc_performance = models.BooleanField(default=False)
    review_data = models.BooleanField(default=False)
    edit_data = models.BooleanField(default=False)
    voice_review = models.BooleanField(default=False)
    callback_qc = models.BooleanField(default=False)
    coding = models.BooleanField(default=False)
    product_matrix_ai = models.BooleanField(default=False)
    statistical_health_check = models.BooleanField(default=False)
    tabulation = models.BooleanField(default=False)
    statistics = models.BooleanField(default=False)
    funnel_analysis = models.BooleanField(default=False)
    conjoint_analysis = models.BooleanField(default=False)
    segmentation_analysis = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'project')
        constraints = [
            models.UniqueConstraint(
                fields=['project'],
                condition=models.Q(is_owner=True),
                name='unique_owner_per_project',
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user.username} membership in {self.project.name}"


class Interview(models.Model):
    """Represents an interview conducted for a project.

    Interviews link a user (the interviewer), a project and optionally a
    person (respondent).  Additional fields capture the outcome code,
    demographic details and whether the interview was completed
    successfully.  The ``created_at`` timestamp allows for time‑based
    performance tracking.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='interviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interviews')
    person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name='interviews')
    status = models.BooleanField(default=False)
    code = models.IntegerField()
    city = models.CharField(max_length=22, blank=True, null=True)
    age = models.IntegerField(blank=True, null=True)
    birth_year = models.IntegerField(blank=True, null=True)
    gender = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Time at which the interviewer first viewed the form for this interview.
    # This corresponds to when a respondent's phone number and details were
    # shown to the interviewer.  It remains null until the interview is
    # actually submitted.
    start_form = models.DateTimeField(null=True, blank=True)

    # Time at which the interview form was submitted.  This is set when the
    # interviewer submits the form.  It remains null for records that have
    # not been submitted.
    end_form = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"Interview {self.pk} in project {self.project_id}"  # type: ignore[str-format]


class Quota(models.Model):
    """Stores target and assigned counts for a combination of dimensions."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='quotas')
    city = models.CharField(max_length=64, blank=True, null=True)
    age_start = models.IntegerField(blank=True, null=True)
    age_end = models.IntegerField(blank=True, null=True)
    gender = models.CharField(
        max_length=10,
        choices=Person.GenderChoices.choices,
        blank=True,
        null=True,
    )
    target_count = models.PositiveIntegerField()
    assigned_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['project', 'city', 'age_start', 'age_end', 'gender'],
                name='unique_quota_dimension',
            )
        ]

    def matches(self, city: Optional[str], age: Optional[int], gender: Optional[str]) -> bool:
        """Return True when the provided demographics fall into this quota."""

        if self.city:
            if not city or city.strip() != self.city:
                return False
        if self.age_start is not None and self.age_end is not None:
            if age is None:
                return False
            if not (self.age_start <= age <= self.age_end):
                return False
        if self.gender:
            if gender != self.gender:
                return False
        return True

    def age_label(self) -> str:
        if self.age_start is None or self.age_end is None:
            return '—'
        return f"{self.age_start}-{self.age_end}"

    def __str__(self) -> str:  # pragma: no cover
        city_part = self.city or 'Any city'
        age_part = self.age_label()
        gender_part = self.gender or 'Any gender'
        return f"Quota<{self.project_id}:{city_part}:{age_part}:{gender_part}>"


# New model to manage call sample assignments for telephone interviews
class CallSample(models.Model):
    """Represents an individual phone number drawn from the respondent bank for a project.

    When quotas are defined for a project via the quota management panel, the
    system draws a random sample of respondent phone numbers for each quota
    cell (typically three times the requested target).  Each record in this
    table corresponds to a single mobile number to be dialed by a telephone
    interviewer.  The record tracks which quota cell it belongs to, which
    project it is part of and which user (if any) has been assigned to call
    it.  Once a call is completed the ``completed`` flag is set and the
    corresponding timestamp recorded.

    The combination of ``project`` and ``mobile`` is unique to ensure that
    the same phone number is never sampled twice for a given project.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='call_samples')
    quota = models.ForeignKey(Quota, on_delete=models.CASCADE, related_name='call_samples')
    person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True)
    mobile = models.ForeignKey(Mobile, on_delete=models.SET_NULL, null=True, blank=True)
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_samples')
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('project', 'mobile')

    def __str__(self) -> str:  # pragma: no cover
        return f"Sample {self.mobile} for {self.project.name}"


class UploadedSampleEntry(models.Model):
    """Stores rows imported from a project's Excel-based sample bank."""

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='uploaded_samples',
    )
    full_name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32)
    city = models.CharField(max_length=100, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    gender = models.CharField(max_length=32, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_from_row = models.PositiveIntegerField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='uploaded_assigned_samples',
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('project', 'phone')
        indexes = [
            models.Index(fields=['project', 'completed']),
            models.Index(fields=['project', 'assigned_to']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"UploadedSample<{self.project_id}:{self.phone}>"


# New model for external database connections (database management panel)
class DatabaseEntry(models.Model):
    """Represents a connection to an external data source.

    Each entry stores the credentials and configuration required to
    synchronise data from an external system (e.g. KoboToolbox) into
    the InsightZen database.  A database entry is associated with a
    project via a foreign key.  The ``status`` field indicates
    whether the last synchronisation attempt succeeded.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='database_entries')
    db_name = models.CharField(max_length=255)
    token = models.CharField(max_length=255)
    asset_id = models.CharField(max_length=255)
    status = models.BooleanField(default=False)
    # Timestamp of the last attempted synchronisation.  Updated by the
    # sync_database_entries management command each time it runs.
    last_sync = models.DateTimeField(null=True, blank=True)

    # Error message from the last synchronisation attempt, if any.  If
    # synchronisation succeeds this field is cleared.  Useful for
    # debugging issues with external data ingestion.
    last_error = models.TextField(blank=True, default='')

    # Manual update tracking
    last_update_requested = models.DateTimeField(null=True, blank=True)
    update_window_start = models.DateTimeField(null=True, blank=True)
    update_attempt_count = models.PositiveIntegerField(default=0)

    # Timestamp of the last successful manual update triggered via the UI.
    last_manual_update = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('project', 'db_name')

    def __str__(self) -> str:  # pragma: no cover
        return f"DB {self.db_name} for {self.project.name}"


class DatabaseEntryEditRequest(models.Model):
    """Tracks submissions whose Enketo edit URLs were generated recently."""

    entry = models.ForeignKey(DatabaseEntry, on_delete=models.CASCADE, related_name='edit_requests')
    submission_id = models.CharField(max_length=64)
    requested_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('entry', 'submission_id')
        indexes = [
            models.Index(fields=['entry', 'requested_at']),
        ]
        ordering = ['-requested_at']

    def __str__(self) -> str:  # pragma: no cover
        return f"Edit request for {_shorten(self.submission_id)} on {self.entry}"


class ReviewTask(models.Model):
    """Represents a QC review assignment for a reviewer."""

    entry = models.ForeignKey(DatabaseEntry, on_delete=models.CASCADE, related_name='review_tasks')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_tasks')
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_review_tasks',
    )
    task_size = models.PositiveIntegerField(default=0)
    reviewed_count = models.PositiveIntegerField(default=0)
    measure_definition = models.JSONField(default=list, blank=True)
    columns = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def mark_reviewed(self) -> None:
        """Update reviewed counters and completion state."""

        self.reviewed_count = self.rows.filter(completed_at__isnull=False).count()
        if self.reviewed_count >= self.task_size and self.completed_at is None:
            self.completed_at = timezone.now()
        self.save(update_fields=['reviewed_count', 'completed_at'])


class ReviewRow(models.Model):
    """Individual submission row assigned within a review task."""

    task = models.ForeignKey(ReviewTask, on_delete=models.CASCADE, related_name='rows')
    submission_id = models.CharField(max_length=64)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    review_submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('task', 'submission_id')
        ordering = ['created_at']


class ReviewAction(models.Model):
    """Audit trail of actions taken while reviewing a row."""

    class Action(models.TextChoices):
        ASSIGNED = 'assigned', 'Assigned'
        STARTED = 'started', 'Started'
        SUBMITTED = 'submitted', 'Submitted'
        UPDATED_CHECKLIST = 'updated_checklist', 'Updated Checklist'

    row = models.ForeignKey(ReviewRow, on_delete=models.CASCADE, related_name='actions')
    action = models.CharField(max_length=32, choices=Action.choices)
    metadata = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']


class ChecklistResponse(models.Model):
    """Stores boolean responses for checklist measures per row."""

    row = models.ForeignKey(ReviewRow, on_delete=models.CASCADE, related_name='checklist_responses')
    measure_id = models.CharField(max_length=128)
    label = models.CharField(max_length=255)
    value = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('row', 'measure_id')


class TableFilterPreset(models.Model):
    """Stores named advanced-filter presets for interactive tables."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='table_filter_presets')
    table_id = models.CharField(max_length=128)
    name = models.CharField(max_length=150)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'table_id', 'name')
        indexes = [
            models.Index(fields=['user', 'table_id']),
        ]
        ordering = ['name']

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.user_id}:{self.table_id}:{self.name}"


class CalendarEvent(models.Model):
    """Stores collaborative events rendered in the global calendar."""

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    reminder_minutes_before = models.PositiveIntegerField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calendar_events_created')
    participants = models.ManyToManyField(User, related_name='calendar_events', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['start']

    def __str__(self) -> str:  # pragma: no cover
        return f"Event<{self.title} {self.start:%Y-%m-%d}>"


def _shorten(value: str, length: int = 8) -> str:
    """Utility to abbreviate identifiers for string representations."""

    if len(value) <= length:
        return value
    return value[:length] + '…'