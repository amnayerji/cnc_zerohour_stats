from uuid import uuid4

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, editable=False)
    modified_at = models.DateTimeField(auto_now=True, editable=False)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class JobRun(BaseModel):
    start_time = models.DateTimeField(default=timezone.now, db_index=True)
    duration = models.DurationField(null=True, blank=True)
    errors = ArrayField(models.TextField(), default=list, blank=True)
    success = models.BooleanField(default=False)

    class Meta:
        ordering = ("-start_time",)

    def __str__(self):
        return f"Job run at {self.start_time}"

    @property
    def loaded_match_count(self):
        return self.matches.count()

    @property
    def loaded_player_count(self):
        return self.players.count()


class Player(BaseModel):
    job_run = models.ForeignKey(to=JobRun, on_delete=models.CASCADE, related_name="players")
    player_name = models.CharField(max_length=100, db_index=True)
    gentool_id = models.CharField(max_length=32, db_index=True, null=True, blank=True)

    class Meta:
        ordering = ("player_name",)

    def __str__(self):
        gentool_id_prefix = f" ({self.gentool_id}) " if self.gentool_id else ""
        return f"{self.player_name}{gentool_id_prefix}"


class Match(BaseModel):
    job_run = models.ForeignKey(to=JobRun, on_delete=models.CASCADE, related_name="matches")
    map = models.CharField(max_length=255)
    replay_url = models.URLField(max_length=500)
    game_version = models.CharField(max_length=10)
    starting_cash = models.IntegerField()
    match_length = models.DurationField()
    match_type = models.CharField(max_length=20)
    match_timestamp = models.DateTimeField()
    replay_size = models.IntegerField(help_text="Size of the replay file in KB")
    replay_uploaded_by = models.ForeignKey(
        to=Player, on_delete=models.CASCADE, related_name="uploaded_matches"
    )
    replay_upload_timestamp = models.DateTimeField(null=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name_plural = "matches"

    def __str__(self):
        return "__".join(p.player.player_name for p in self.players.all())


class MatchPlayer(BaseModel):
    match = models.ForeignKey(to=Match, on_delete=models.CASCADE, related_name="players")
    player = models.ForeignKey(to=Player, on_delete=models.CASCADE, related_name="matches")
    team = models.IntegerField(null=True, blank=True)
    army = models.CharField(max_length=25)

    class Meta:
        ordering = ("team",)

    def __str__(self):
        return f"{self.player.player_name} ({self.army} - Team {self.team})"
