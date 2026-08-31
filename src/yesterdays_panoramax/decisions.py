"""Per-image federation control.

Everything else in this package decides what to publish from *properties* of an
image -- its licence, its visibility, whether it has a date and a georeference.
That is the right default, but it cannot express a judgement about one specific
photograph: a portrait whose subject asked not to be republished, a scan whose
provenance turned out to be murky, a plate the archivist wants held back
pending review.

An ``ImageDecision`` records that judgement, and only that. Rows exist only for
images somebody has ruled on; absence means "no opinion, apply the usual
rules", which is why turning this feature on changes nothing until a decision
is actually made.

It lives in its own module rather than in ``models.py`` because ``queries``
needs it and ``models`` needs ``queries``; importing it here keeps that a line
rather than a cycle. ``models`` re-exports it so Django registers it with the
app.

Note this is a control over *publication*, not a deletion mechanism. Excluding
an image drops it from the collection's item listing and bumps the collection's
``updated``; the harvester replaces a collection's items wholesale on its next
pass, deleting the ones no longer present, so the picture leaves the federation
on its own. It does not touch the image on this instance.
"""

from django.conf import settings
from django.db import models

#: Approve this image for publication. Required under the opt-in policy. It is
#: an approval, not an override: an approved image still has to satisfy the
#: licence, visibility, date and georeference rules. Letting a human tick a box
#: past the licence gate is precisely what that gate exists to prevent.
INCLUDE = "include"
#: Never publish this image, whatever every other rule says. Exclusion is the
#: one decision that is absolute, because it is the one that can only ever
#: publish less.
EXCLUDE = "exclude"

DECISIONS = [
    (INCLUDE, "Include in the federation"),
    (EXCLUDE, "Exclude from the federation"),
]


class ImageDecision(models.Model):
    """An explicit ruling about one image, overriding the eligibility rules."""

    image = models.OneToOneField(
        "images.Image",
        on_delete=models.CASCADE,
        related_name="panoramax_decision",
    )
    decision = models.CharField(max_length=10, choices=DECISIONS, db_index=True)

    # Why, and by whom. A federation opt-out is the kind of thing somebody asks
    # about a year later, usually because the person who requested it has come
    # back with a further question.
    reason = models.TextField(
        blank=True,
        default="",
        help_text="Why this ruling was made. Shown to nobody outside the admin.",
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="panoramax_decisions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "image federation decision"
        verbose_name_plural = "image federation decisions"

    def __str__(self):
        return f"Image {self.image_id}: {self.get_decision_display().lower()}"

    @property
    def excludes(self) -> bool:
        return self.decision == EXCLUDE
