"""Django admin configuration for core models."""

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Profile, Person, Mobile, Project, Membership, Interview, Quota, ActivityLog


class ProfileInline(admin.StackedInline):
    """Allows editing of the Profile model on the same page as the User model."""
    model = Profile
    can_delete = False
    verbose_name_plural = 'profile'


class UserAdmin(BaseUserAdmin):
    """Extend the default User admin to include Profile fields."""
    inlines = (ProfileInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(Project)
admin.site.register(Membership)
admin.site.register(Person)
admin.site.register(Mobile)
admin.site.register(Interview)
admin.site.register(Quota)
admin.site.register(ActivityLog)