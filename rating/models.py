from django.conf import settings
from django.db import models


class RatingHistory(models.Model):
    """Снимок рейтинга спортсмена после каждого пересчёта, в котором он изменился."""
    athlete = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rating_history")
    value = models.FloatField()
    position = models.PositiveIntegerField(null=True)
    delta = models.FloatField(default=0)
    reason = models.CharField(max_length=200, blank=True)
    competition = models.ForeignKey("competitions.Competition", null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "история рейтинга"
        verbose_name_plural = "история рейтинга"
