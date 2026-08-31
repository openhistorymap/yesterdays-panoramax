import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Federation state for the Panoramax adapter.

    Deliberately self-contained: the adapter adds no column to the ``images``
    tables, so it can be enabled on an existing installation by adding the app
    and running this one migration. Federated identifiers are derived from
    primary keys instead of stored on them (see ``panoramax.ids``).
    """

    initial = True

    # "__first__" rather than a pinned name: the host application owns its
    # own migration history, and this package must not assume what it called
    # the migration that created images.Collection.
    dependencies = [
        ("images", "__first__"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublishedCollection",
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
                ("collection_pk", models.BigIntegerField(editable=False, unique=True)),
                ("uuid", models.UUIDField(editable=False, unique=True)),
                ("published", models.BooleanField(db_index=True, default=False)),
                ("item_count", models.PositiveIntegerField(default=0)),
                (
                    "license_label",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                ("created", models.DateTimeField()),
                ("updated", models.DateTimeField(db_index=True)),
                ("first_published_at", models.DateTimeField(blank=True, null=True)),
                ("unpublished_at", models.DateTimeField(blank=True, null=True)),
                ("min_x", models.FloatField(blank=True, null=True)),
                ("min_y", models.FloatField(blank=True, null=True)),
                ("max_x", models.FloatField(blank=True, null=True)),
                ("max_y", models.FloatField(blank=True, null=True)),
                ("start_datetime", models.DateTimeField(blank=True, null=True)),
                ("end_datetime", models.DateTimeField(blank=True, null=True)),
                (
                    "collection",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="panoramax_state",
                        to="images.collection",
                    ),
                ),
            ],
            options={
                "verbose_name": "published collection",
                "ordering": ["updated", "collection_pk"],
            },
        ),
        migrations.AddIndex(
            model_name="publishedcollection",
            index=models.Index(
                fields=["updated", "collection_pk"],
                name="panoramax_updated_pk_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="publishedcollection",
            index=models.Index(
                fields=["published", "updated"],
                name="panoramax_pub_updated_idx",
            ),
        ),
    ]
