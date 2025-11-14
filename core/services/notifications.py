"""Utility helpers for creating and dispatching user notifications."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from django.contrib.auth.models import User

from core.models import CalendarEvent, Membership, Notification, Project


def _user_display(user: User | None) -> str:
    """Return a readable label for the given user."""

    if not user:
        return ''
    full_name = user.get_full_name()
    if full_name:
        return full_name
    if user.first_name:
        return user.first_name
    return user.username


def _build_messages(en: str, fa: str | None = None) -> Dict[str, Dict[str, str]]:
    """Prepare a metadata payload containing bilingual messages."""

    persian = fa or en
    return {'messages': {'en': en, 'fa': persian}}


def create_notification(
    recipient: User,
    *,
    message_en: str,
    message_fa: str | None = None,
    event_type: str,
    project: Project | None = None,
    extra_metadata: Dict[str, Any] | None = None,
) -> Notification:
    """Create a notification with bilingual messaging support."""

    metadata: Dict[str, Any] = _build_messages(message_en, message_fa)
    if extra_metadata:
        metadata.update(extra_metadata)
    return Notification.objects.create(
        recipient=recipient,
        project=project,
        message=message_en,
        event_type=event_type,
        metadata=metadata,
    )


def notify_membership_added(membership: Membership, actor: User | None = None) -> Notification:
    """Send a notification when a user is assigned to a project."""

    actor_name = _user_display(actor)
    project_name = membership.project.name
    message_en = f"You were added to project \"{project_name}\"."
    if actor_name:
        message_en = f"{actor_name} added you to project \"{project_name}\"."
    message_fa = (
        f"{actor_name} شما را به پروژه «{project_name}» اضافه کرد."
        if actor_name
        else f"شما به پروژه «{project_name}» اضافه شدید."
    )
    return create_notification(
        membership.user,
        message_en=message_en,
        message_fa=message_fa,
        event_type=Notification.EventType.MEMBERSHIP_ADDED,
        project=membership.project,
        extra_metadata={
            'project_id': membership.project_id,
            'actor': actor_name,
        },
    )


def notify_project_started(project: Project, initiator: User | None = None) -> None:
    """Broadcast a project start notification to existing members."""

    memberships = Membership.objects.filter(project=project).select_related('user')
    if not memberships.exists():
        return
    actor_name = _user_display(initiator)
    for membership in memberships:
        project_name = project.name
        message_en = f"Project \"{project_name}\" has started."
        message_fa = f"پروژه «{project_name}» آغاز شد."
        if actor_name:
            message_en = f"{actor_name} started project \"{project_name}\"."
            message_fa = f"{actor_name} پروژه «{project_name}» را آغاز کرد."
        create_notification(
            membership.user,
            message_en=message_en,
            message_fa=message_fa,
            event_type=Notification.EventType.PROJECT_STARTED,
            project=project,
            extra_metadata={'project_id': project.pk, 'actor': actor_name},
        )


def ensure_project_deadline_notifications(project: Project) -> None:
    """Ensure each project member is notified that the deadline has passed."""

    existing = set(
        Notification.objects.filter(
            project=project,
            event_type=Notification.EventType.PROJECT_DEADLINE,
        ).values_list('recipient_id', flat=True)
    )
    memberships = Membership.objects.filter(project=project).select_related('user')
    if not memberships.exists():
        return
    project_name = project.name
    for membership in memberships:
        if membership.user_id in existing:
            continue
        message_en = (
            f'The deadline for project "{project_name}" has passed. Access is limited to the owner.'
        )
        message_fa = f"ددلاین پروژه «{project_name}» به پایان رسیده و دسترسی تنها برای مالک فعال است."
        create_notification(
            membership.user,
            message_en=message_en,
            message_fa=message_fa,
            event_type=Notification.EventType.PROJECT_DEADLINE,
            project=project,
            extra_metadata={'project_id': project.pk},
        )


def notify_custom_message(
    recipients: Iterable[User],
    *,
    message_en: str,
    message_fa: str | None = None,
    actor: User | None = None,
) -> List[Notification]:
    """Send a custom notification to one or more recipients."""

    created: List[Notification] = []
    actor_name = _user_display(actor)
    fallback = message_fa or message_en
    for recipient in recipients:
        metadata: Dict[str, Any] = {}
        if actor_name:
            metadata['actor'] = actor_name
        created.append(
            create_notification(
                recipient,
                message_en=message_en,
                message_fa=fallback,
                event_type=Notification.EventType.CUSTOM_MESSAGE,
                project=None,
                extra_metadata=metadata or None,
            )
        )
    return created


def _format_datetime(dt) -> str:
    """Return a readable timestamp string."""

    return dt.strftime('%Y-%m-%d %H:%M')


def _event_context(event: CalendarEvent) -> Dict[str, Any]:
    return {
        'event_id': event.pk,
        'title': event.title,
        'start': event.start.isoformat(),
        'end': event.end.isoformat(),
    }


def notify_event_invite(
    event: CalendarEvent,
    recipients: Sequence[User],
    *,
    actor: User | None = None,
) -> None:
    """Notify users that they were added to an event."""

    if not recipients:
        return
    actor_name = _user_display(actor)
    start_label = _format_datetime(event.start)
    for recipient in recipients:
        message_en = f'You were invited to "{event.title}" on {start_label}.'
        message_fa = f'به رویداد «{event.title}» در {start_label} دعوت شدید.'
        if actor_name:
            message_en = f"{actor_name} invited you to \"{event.title}\" on {start_label}."
            message_fa = f"{actor_name} شما را به رویداد «{event.title}» در {start_label} دعوت کرد."
        create_notification(
            recipient,
            message_en=message_en,
            message_fa=message_fa,
            event_type=Notification.EventType.EVENT_INVITE,
            project=None,
            extra_metadata=_event_context(event),
        )


def notify_event_update(
    event: CalendarEvent,
    recipients: Sequence[User],
    *,
    actor: User | None = None,
) -> None:
    """Notify attendees that an event changed."""

    if not recipients:
        return
    actor_name = _user_display(actor)
    start_label = _format_datetime(event.start)
    for recipient in recipients:
        message_en = f'Event "{event.title}" was updated ({start_label}).'
        message_fa = f"رویداد «{event.title}» برای {start_label} به‌روزرسانی شد."
        if actor_name:
            message_en = f"{actor_name} updated \"{event.title}\" ({start_label})."
            message_fa = f"{actor_name} رویداد «{event.title}» را برای {start_label} به‌روزرسانی کرد."
        create_notification(
            recipient,
            message_en=message_en,
            message_fa=message_fa,
            event_type=Notification.EventType.EVENT_UPDATE,
            project=None,
            extra_metadata=_event_context(event),
        )


def notify_event_reminder(event: CalendarEvent, recipients: Sequence[User]) -> None:
    """Send reminder notifications for the event."""

    if not recipients:
        return
    start_label = _format_datetime(event.start)
    for recipient in recipients:
        message_en = f'Reminder: "{event.title}" starts at {start_label}.'
        message_fa = f"یادآوری: رویداد «{event.title}» در {start_label} آغاز می‌شود."
        create_notification(
            recipient,
            message_en=message_en,
            message_fa=message_fa,
            event_type=Notification.EventType.EVENT_REMINDER,
            project=None,
            extra_metadata=_event_context(event),
        )

def localised_message(notification: Notification, lang: str) -> str:
    """Return the notification message for the requested language."""

    payload = notification.metadata or {}
    messages = payload.get('messages', {})
    return messages.get(lang) or messages.get('en') or notification.message


def mark_notifications_read(recipient: User, notification_ids: Iterable[int] | None = None) -> int:
    """Mark notifications as read for the recipient."""

    qs = Notification.objects.filter(recipient=recipient, is_read=False)
    if notification_ids is not None:
        ids = list(notification_ids)
        if not ids:
            return 0
        qs = qs.filter(pk__in=ids)
    updated = qs.update(is_read=True)
    return int(updated)
