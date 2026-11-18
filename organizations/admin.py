from django.contrib import admin

from .models import (
    AccessProfile,
    JobTitle,
    Membership,
    Organization,
    Team,
    Scope,
)

@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "country_code",
        "time_zone",
        "default_locale",
        "work_mode",
        "version",
    )

    list_filter = (
        "country_code",
        "default_locale",
        "work_mode",
    )

    search_fields = ("name",)

    readonly_fields = (
        "id",
        "version",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "organization",
        "kind",
        "is_active",
        "version",
    )

    list_filter = (
        "kind",
        "is_active",
    )

    search_fields = (
        "name",
        "organization__name",
    )

    list_select_related = ("organization",)

    readonly_fields = (
        "id",
        "version",
        "created_at",
        "updated_at",
    )

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Membership)
class MembershipAdmin(ReadOnlyAdmin):
    list_display = (
        "user",
        "organization",
        "team",
        "job_title",
        "participant_type",
        "system_role",
        "rank",
        "access_profile",
        "is_active",
    )

    list_filter = (
        "participant_type",
        "system_role",
        "is_active",
    )

    search_fields = (
        "user__username",
        "user__email",
        "organization__name",
        "team__name",
        "job_title__name",
    )

    list_select_related = (
        "user",
        "organization",
        "team",
        "job_title",
        "access_profile",
    )


@admin.register(AccessProfile)
class AccessProfileAdmin(ReadOnlyAdmin):
    list_display = (
        "name",
        "organization",
        "is_active",
        "version",
    )

    list_filter = ("is_active",)

    search_fields = (
        "name",
        "organization__name",
    )

    list_select_related = ("organization",)

@admin.register(JobTitle)
class JobTitleAdmin(ReadOnlyAdmin):
    list_display = (
        "name",
        "organization",
        "is_active",
        "version",
    )

    list_filter = ("is_active",)

    search_fields = (
        "name",
        "organization__name",
    )

    list_select_related = ("organization",)

@admin.register(Scope)
class ScopeAdmin(ReadOnlyAdmin):
    list_display = (
        "membership",
        "capability",
        "kind",
        "team",
    )

    list_filter = (
        "kind",
        "capability",
    )

    search_fields = (
        "membership__user__username",
        "membership__organization__name",
        "team__name",
    )

    list_select_related = (
        "membership",
        "membership__user",
        "membership__organization",
        "team",
    )