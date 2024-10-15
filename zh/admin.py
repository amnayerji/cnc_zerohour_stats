import json

from django.contrib import admin
from django.contrib.admin import ModelAdmin, TabularInline
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import JsonLexer

from zh.models import JobRun, Match, MatchPlayer, Player


class ReadOnlyMixin:

    def has_add_permission(self, *_args, **_kwargs):
        return False

    def has_change_permission(self, *_args, **_kwargs):
        return False

    def has_delete_permission(self, *_args, **_kwargs):
        return False

    def has_view_permission(self, *_args, **_kwargs):
        return True


class BaseModelAdmin(ModelAdmin):
    readonly_fields = ("id", "created_at", "modified_at")


@admin.register(JobRun)
class JobRunAdmin(ReadOnlyMixin, BaseModelAdmin):
    list_display = ("id", "start_time", "duration", "success")
    list_filter = ("success",)
    search_fields = ("id", "last_loaded_month", "last_loaded_date")
    date_hierarchy = "start_time"
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "start_time",
                    "duration",
                    "success",
                    "loaded_matches",
                    "last_loaded_month",
                    "last_loaded_date",
                    "id",
                    "created_at",
                    "modified_at",
                )
            },
        ),
        (
            "Logs",
            {
                "fields": ("pretty_logs",),
            },
        ),
    )

    def pretty_logs(self, obj):
        # TODO: add this to ella, instead?  (sc73903)
        formatter = HtmlFormatter(style="github-dark")
        prettified_data = highlight(
            json.dumps(obj.logs, indent=2, sort_keys=True),
            JsonLexer(),
            formatter,
        )
        return mark_safe(f"<style>{formatter.get_style_defs()}</style>{prettified_data}")

    pretty_logs.short_description = ""


@admin.register(Player)
class Player(ReadOnlyMixin, BaseModelAdmin):
    list_display = ("id", "player_name", "gentool_id")
    search_fields = ("id", "player_name", "gentool_id")


class MatchPlayerInline(ReadOnlyMixin, TabularInline):
    model = MatchPlayer
    fields = ("match", "player", "team", "army")
    extra = 0


@admin.register(Match)
class MatchAdmin(ReadOnlyMixin, BaseModelAdmin):
    list_display = ("id", "match_datetime", "match_type", "map", "starting_cash", "match_length")
    list_filter = (
        "game_version",
        "match_type",
        "players__player__player_name",
        "replay_uploaded_by__player_name",
        "players__army",
    )
    search_fields = (
        "id",
        "map",
        "replay_url",
        "players__player__player_name",
        "replay_uploaded_by__player_name",
        "players__army",
    )
    date_hierarchy = "match_datetime"
    inlines = (MatchPlayerInline,)
