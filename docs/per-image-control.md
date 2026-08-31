# Per-image federation control

Everything else in this package decides what to publish from *properties* of an
image — its licence, its visibility, whether it has a date and a georeference.
That is the right default, and for most archives it is the whole story.

It cannot, though, express a judgement about one particular photograph: a
portrait whose subject has asked not to have it republished, a scan whose
provenance turned out to be murkier than the licence field suggests, a plate an
archivist wants held back pending review. That is what this is for.

The feature is **inert until used**. With no decisions recorded, the default
policy behaves exactly as it did before the model existed.

## Two policies

```python
PANORAMAX_IMAGE_POLICY = "opt-out"   # the default
PANORAMAX_IMAGE_POLICY = "opt-in"
```

**`opt-out`** publishes everything the eligibility rules allow, minus images
explicitly excluded. An image nobody has ruled on is published.

**`opt-in`** inverts it: nothing is published until an image has been
explicitly approved. This is what an archive wants when rights are settled
picture by picture rather than licence by licence — a collection of donated
prints, say, where permission was negotiated individually.

An unrecognised value raises `ImproperlyConfigured` rather than falling back.
Silently defaulting a typo to `opt-out` would publish an entire archive
somebody meant to curate, and the federation does not forget quickly.

## Approval is not an override

An **exclusion is absolute**. Whatever the licence says, whatever the policy
is, an excluded image is never published. Exclusion can only ever publish
*less*, so there is no reason to qualify it.

An **approval is not**. An approved image still has to satisfy every other
rule: licence, visibility, date, georeference. Letting a human tick a box past
the licence gate is precisely what that gate exists to prevent, and an approved
image with no georeference has no geometry to publish regardless of anyone's
intentions.

So `api.is_published(image)` reports the *whole* test, not just the ruling —
which is what a host UI should show, because "approved" and "published" are not
the same state.

## From your own code

The package cannot add a checkbox to Yesterdays' image page; that template
belongs to the host. What it offers is a small stable surface to call from your
own views, admin actions or API:

```python
from yesterdays_panoramax import api

api.exclude_image(image, reason="Depicted person objected", by=request.user)
api.include_image(image, reason="Rights confirmed", by=request.user)
api.clear_decision(image)          # back to the ordinary rules

api.decision_for(image)            # "include" | "exclude" | None
api.is_published(image)            # the whole test, not just the ruling
```

Each helper takes a model instance or a primary key, and each schedules the
collection refresh that carries the change into the federation, so callers do
not need to know federation state exists.

There is also a Django admin for `ImageDecision` — editable, unlike
`PublishedCollection`, because this is the one piece of federation state a
human is supposed to author. It records who decided and why; a federation
opt-out is the kind of thing somebody asks about a year later, usually because
the person who requested it has come back with a further question.

## In bulk

The admin is fine for ruling on one photograph. Curating an archive is not —
under `opt-in`, approving ten thousand plates one at a time is not a workflow.

```
manage.py panoramax_decide include --collection 42
manage.py panoramax_decide exclude --image 17 --image 18 --reason "rights unclear"
manage.py panoramax_decide clear --collection 42
manage.py panoramax_decide include --collection 42 --dry-run
```

`--image` and `--collection` may each be repeated and may be combined.

## What exclusion actually does

It does not touch the image on your instance, and it does not send a delete to
anybody. It drops the picture from its collection's item listing and bumps the
collection's `updated`.

That is sufficient, because of how the harvester works: on every pass it
re-fetches a collection's items into a temporary table and deletes the rows for
that collection that are no longer present. So the picture leaves the central
catalogue on the next harvest, on its own.

Two consequences worth knowing:

- **It is not immediate.** The picture is gone from your API at once, but stays
  in the federation until the next harvest of that collection.
- **Excluding the last eligible image in a collection tombstones the
  collection**, which is what withdraws the collection itself. See
  [operations](operations.md#withdrawing-cleanly).

## Storage

One table, `panoramax_imagedecision`, with a row only for images somebody has
ruled on — absence means "no opinion". It hangs off `images.Image` with
`on_delete=CASCADE`, so deleting an image takes its ruling with it.

Nothing is added to the `images` tables, as everywhere else in this package.
