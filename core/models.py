"""Data models for the InsightZen application.

This module defines the database schema for the application using Django's
ORM. The models here reflect the latest specifications provided by the
user, including a more expressive membership model, a rich person
registry with associated mobile numbers, a table for interviews and a
quota table used by the quota management panel.  The ``Project`` model
no longer stores an owner directly; instead project ownership and panel
permissions are governed exclusively via the ``Membership`` model.
"""

from __future__ import annotations

from django.db import models
from django.contrib.auth.models import User
from django.contrib.postgres.fields import ArrayField  # type: ignore


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
    """Represents an individual respondent.

    Each person is uniquely identified by their ``national_code``.  The
    person record contains basic demographic attributes and optional
    location metadata.  The ``imputation`` flag can be used by future
    extensions to mark records that were imputed rather than collected
    directly.
    """

    national_code = models.CharField(max_length=10, primary_key=True)
    full_name = models.CharField(max_length=145, blank=True, null=True)
    father_name = models.CharField(max_length=35, blank=True, null=True)
    birth_year = models.IntegerField()
    birth_date = models.CharField(max_length=10, blank=True, null=True)
    city_name = models.CharField(max_length=22)
    province_name = models.CharField(max_length=20, blank=True, null=True)
    birth_city = models.CharField(max_length=22, blank=True, null=True)
    birth_province = models.CharField(max_length=20, blank=True, null=True)
    imputation = models.BooleanField(default=False)

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

    Projects do not store a direct ``owner`` attribute; instead, project
    ownership and panel access are managed via the ``Membership`` model.
    The ``filled_samples`` field tracks the number of completed
    interviews and is automatically initialised to zero.
    """

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

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Membership(models.Model):
    """Associates a user with a project and records panel permissions.

    Each membership record indicates which panels a user may access for
    a given project.  The ``start_work`` date captures when the
    association was created.  Panel names are stored as boolean flags
    corresponding to the list provided by the user, omitting the
    ``User Management`` and ``Project Management`` panels which are
    reserved for organisation administrators.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    start_work = models.DateField(auto_now_add=True)
    # Optional title to describe this membership (e.g. role or label).
    title = models.CharField(max_length=100, blank=True, null=True)
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
    voice_review = models.BooleanField(default=False)
    callback_qc = models.BooleanField(default=False)
    coding = models.BooleanField(default=False)
    statistical_health_check = models.BooleanField(default=False)
    tabulation = models.BooleanField(default=False)
    statistics = models.BooleanField(default=False)
    funnel_analysis = models.BooleanField(default=False)
    conjoint_analysis = models.BooleanField(default=False)
    segmentation_analysis = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'project')

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
    """Stores target and assigned counts for each city and age range.

    Each quota row corresponds to a combination of city and age range
    within a project.  The ``target_count`` is calculated from the
    quotas specified by the user in the quota management panel.  As
    interviews are assigned and completed, the ``assigned_count`` can be
    incremented to track progress against the target.
    """

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='quotas')
    city = models.CharField(max_length=22)
    age_start = models.IntegerField()
    age_end = models.IntegerField()
    target_count = models.PositiveIntegerField()
    assigned_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('project', 'city', 'age_start', 'age_end')

    def __str__(self) -> str:  # pragma: no cover
        return f"Quota for {self.city} ages {self.age_start}-{self.age_end} in {self.project.name}"


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

    class Meta:
        unique_together = ('project', 'db_name')

    def __str__(self) -> str:  # pragma: no cover
        return f"DB {self.db_name} for {self.project.name}"