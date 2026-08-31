"""Turning Yesterdays' EDTF dates into the timestamps STAC requires.

The meta-catalogue stores ``datetime TIMESTAMPTZ NOT NULL`` per item, but a
Yesterdays image carries an EDTF string, which is frequently a range ("1890s",
"192X", "1901-06") rather than an instant. STAC's answer to that is the
datetime-range form from the common metadata spec: ``start_datetime`` and
``end_datetime`` describing the range, and ``datetime`` pinned to a single
representative instant.

We pin ``datetime`` to the *start* of the range rather than its midpoint. A
midpoint is a value no source ever asserted, and it drifts as soon as the range
is widened; the start is the earliest moment the photograph could have been
taken, which is a claim the archive actually makes.

``Image.save`` already rejects unparseable and open-ended EDTF, so anything
stored is a bounded range -- but this module is defensive anyway, because it
runs against rows written before that validation existed.
"""

import datetime as dt

from edtf import parse_edtf
from edtf.parser.edtf_exceptions import EDTFParseException

# datetime.MINYEAR is 1, but Postgres timestamptz and most STAC clients are
# happier well inside that. Anything outside this window is treated as unusable
# rather than published as a nonsense date.
MIN_YEAR = 1
MAX_YEAR = 9999


def _to_datetime(struct, *, end_of_second=False):
    """Convert an EDTF ``struct_time`` into an aware UTC datetime."""
    try:
        year, month, day, hour, minute, second = (
            struct[0],
            struct[1] or 1,
            struct[2] or 1,
            struct[3] or 0,
            struct[4] or 0,
            struct[5] or 0,
        )
    except (IndexError, TypeError):
        return None
    if not MIN_YEAR <= year <= MAX_YEAR:
        return None
    # EDTF's upper bound for a coarse date lands on the last second of the
    # period; leap seconds occasionally push tm_sec to 60, which datetime
    # rejects outright.
    second = min(second, 59)
    try:
        return dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.UTC)
    except ValueError:
        return None


def edtf_interval(edtf_date):
    """Return ``(start, end)`` as aware UTC datetimes, or ``(None, None)``.

    ``end`` is never earlier than ``start``; a source that manages to store an
    inverted range is collapsed to an instant rather than published as one.
    """
    if not edtf_date:
        return None, None
    try:
        parsed = parse_edtf(str(edtf_date))
    except (EDTFParseException, TypeError, ValueError):
        return None, None

    try:
        start = _to_datetime(parsed.lower_strict())
        end = _to_datetime(parsed.upper_strict())
    except (AttributeError, TypeError, ValueError):
        return None, None

    if start is None:
        return None, None
    if end is None or end < start:
        end = start
    return start, end


def is_instant(start, end):
    """Whether the range is narrow enough to publish as a single datetime.

    A range that resolves to the same second needs no ``start_datetime`` /
    ``end_datetime`` pair.
    """
    return start is not None and end is not None and start == end


def rfc3339(value):
    """Format an aware datetime the way STAC expects."""
    if value is None:
        return None
    return value.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
