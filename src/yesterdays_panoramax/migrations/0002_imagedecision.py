import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Per-image federation control.

    Purely additive, and inert until a row exists: with no decisions recorded,
    the default opt-out policy behaves exactly as before.
    """

    dependencies = [
        ("panoramax", "0001_initial"),
        ("images", "__first__"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ImageDecision",
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
                (
                    "decision",
                    models.CharField(
                        choices=[
                            ("include", "Include in the federation"),
                            ("exclude", "Exclude from the federation"),
                        ],
                        db_index=True,
                        max_length=10,
                    ),
                ),
                (
                    "reason",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text=(
                            "Why this ruling was made. Shown to nobody outside "
                            "the admin."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "image",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="panoramax_decision",
                        to="images.image",
                    ),
                ),
                (
                    "decided_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="panoramax_decisions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "image federation decision",
                "verbose_name_plural": "image federation decisions",
                "ordering": ["-updated_at"],
            },
        ),
    ]
