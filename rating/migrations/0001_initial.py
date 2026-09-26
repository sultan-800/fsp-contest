import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("competitions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RatingHistory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("value", models.FloatField()),
                ("position", models.PositiveIntegerField(null=True)),
                ("delta", models.FloatField(default=0)),
                ("reason", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "athlete",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rating_history",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "competition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="competitions.competition",
                    ),
                ),
            ],
            options={
                "verbose_name": "история рейтинга",
                "verbose_name_plural": "история рейтинга",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
