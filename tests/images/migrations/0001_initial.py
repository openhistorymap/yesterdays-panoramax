import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Schema for the stubbed host app. Not shipped -- see tests/images."""

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="License",
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
                ("name", models.CharField(max_length=500)),
                ("display_name", models.CharField(max_length=500)),
                ("permalink", models.URLField(blank=True, null=True)),
            ],
        ),
        migrations.CreateModel(
            name="Source",
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
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField(unique=True)),
                ("url", models.URLField(blank=True)),
                ("description", models.TextField(blank=True)),
                ("public", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Collection",
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
                ("name", models.CharField(max_length=200)),
                ("slug", models.SlugField()),
                ("url", models.URLField(blank=True)),
                ("description", models.TextField(blank=True)),
                ("public", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collections",
                        to="images.source",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Image",
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
                ("title", models.CharField(max_length=500)),
                ("permalink", models.URLField()),
                ("thumbnail", models.URLField(blank=True, null=True)),
                ("transformed_permalink", models.URLField(blank=True, null=True)),
                ("original_url", models.URLField(blank=True, null=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("creator", models.CharField(blank=True, max_length=100, null=True)),
                ("ref", models.CharField(blank=True, max_length=100, null=True)),
                (
                    "original_date",
                    models.CharField(blank=True, max_length=50, null=True),
                ),
                ("edtf_date", models.CharField(blank=True, max_length=50, null=True)),
                ("start_decdate", models.IntegerField(blank=True, null=True)),
                ("end_decdate", models.IntegerField(blank=True, null=True)),
                ("aerial", models.BooleanField(default=False)),
                ("will_not_georef", models.BooleanField(default=False)),
                (
                    "rotation",
                    models.IntegerField(
                        choices=[(0, "None"), (90, "90"), (180, "180"), (270, "270")],
                        default=0,
                    ),
                ),
                (
                    "mirror",
                    models.CharField(
                        choices=[
                            ("none", "None"),
                            ("h", "Horizontal"),
                            ("v", "Vertical"),
                        ],
                        default="none",
                        max_length=4,
                    ),
                ),
                ("iiif_url", models.URLField(blank=True, null=True)),
                ("width", models.PositiveIntegerField(blank=True, null=True)),
                ("height", models.PositiveIntegerField(blank=True, null=True)),
                ("is_searchable", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "collection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="images",
                        to="images.collection",
                    ),
                ),
                (
                    "duplicate_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="duplicates",
                        to="images.image",
                    ),
                ),
                (
                    "license",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="images",
                        to="images.license",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Georeference",
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
                ("point", django.contrib.gis.db.models.fields.PointField(srid=4326)),
                ("direction", models.IntegerField(blank=True, null=True)),
                (
                    "confidence",
                    models.CharField(
                        choices=[
                            ("low", "Low"),
                            ("medium", "Medium"),
                            ("high", "High"),
                        ],
                        default="medium",
                        max_length=10,
                    ),
                ),
                ("georeferenced_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "image",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="georeferences",
                        to="images.image",
                    ),
                ),
                (
                    "georeferenced_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="georeferenced_images",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
