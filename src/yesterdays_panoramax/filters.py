"""The slice of CQL2 the harvester actually sends.

Every incremental harvest issues exactly one filter::

    ?filter=status IN ('deleted','ready') AND updated > '2026-08-30T07:00:00Z'

so this parses that shape rather than implementing CQL2. (Panoramax's own
server runs a deliberately lax fork of cql2-rs for the same reason: the
expression is machine-generated and narrow.)

An unrecognised clause is **ignored with a warning, not rejected**. The two
failure modes are not symmetric. Ignoring a clause we do not understand widens
the result set, so the harvester does more work than it needed to and still
sees everything. Rejecting the request -- or worse, silently narrowing it --
stops the harvest dead or drops collections on the floor without anyone
noticing. If a future harvester sends a filter we have never seen, this
instance degrades to full listings instead of falling out of the federation.
"""

import datetime as dt
import logging
import re
from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

_STATUS_IN = re.compile(r"\bstatus\s+IN\s*\(([^)]*)\)", re.IGNORECASE)
_STATUS_EQ = re.compile(r"\bstatus\s*=\s*'([^']*)'", re.IGNORECASE)
_TIMESTAMP = re.compile(r"\b(updated|created)\s*(>=|<=|>|<)\s*'([^']*)'", re.IGNORECASE)
_QUOTED = re.compile(r"'([^']*)'")

READY = "ready"
DELETED = "deleted"


@dataclass
class CollectionFilter:
    """A parsed ``filter=`` expression, reduced to what we can honour."""

    statuses: set[str] = field(default_factory=set)
    updated_after: dt.datetime | None = None
    updated_after_inclusive: bool = False
    created_after: dt.datetime | None = None
    created_after_inclusive: bool = False

    @property
    def wants_ready(self) -> bool:
        return not self.statuses or READY in self.statuses

    @property
    def wants_deleted(self) -> bool:
        # Deliberately *not* symmetric with wants_ready. A listing with no
        # status clause -- a browser, or a harvester's very first crawl -- wants
        # the live catalogue, not a graveyard. Tombstones are only interesting
        # to an incremental harvest, and that always asks for them by name.
        return DELETED in self.statuses


def _as_aware(value):
    parsed = parse_datetime(value.strip())
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        # dt.timezone.utc, not timezone.utc: Django removed the latter in 5.0,
        # and the harvester's filter carries a bare date often enough
        # ("updated > '2026-01-01'") for this path to be live.
        return timezone.make_aware(parsed, dt.UTC)
    return parsed


def parse(expression) -> CollectionFilter:
    """Parse a ``filter=`` expression into a :class:`CollectionFilter`."""
    result = CollectionFilter()
    if not expression:
        return result

    remainder = expression

    match = _STATUS_IN.search(remainder)
    if match:
        result.statuses = {
            value.strip().lower() for value in _QUOTED.findall(match.group(1))
        }
        remainder = remainder.replace(match.group(0), "", 1)
    else:
        match = _STATUS_EQ.search(remainder)
        if match:
            result.statuses = {match.group(1).strip().lower()}
            remainder = remainder.replace(match.group(0), "", 1)

    for match in _TIMESTAMP.finditer(expression):
        field_name = match.group(1).lower()
        operator, raw = match.group(2), match.group(3)
        moment = _as_aware(raw)
        remainder = remainder.replace(match.group(0), "", 1)
        if moment is None:
            logger.warning("Panoramax filter: unparseable timestamp %r", raw)
            continue
        if operator not in (">", ">="):
            # Upper bounds would narrow the result set; ignoring them is the
            # safe direction, and no harvester sends one.
            logger.warning(
                "Panoramax filter: ignoring unsupported operator %r on %s",
                operator,
                field_name,
            )
            continue
        if field_name == "updated":
            result.updated_after = moment
            result.updated_after_inclusive = operator == ">="
        else:
            result.created_after = moment
            result.created_after_inclusive = operator == ">="

    leftover = re.sub(r"\b(AND|OR)\b", " ", remainder, flags=re.IGNORECASE).strip()
    if leftover:
        logger.warning(
            "Panoramax filter: ignoring unrecognised clause %r (serving a wider "
            "result set rather than failing the harvest)",
            leftover,
        )
    return result


def apply(queryset, parsed: CollectionFilter):
    """Narrow a ``PublishedCollection`` queryset by a parsed filter."""
    if parsed.updated_after is not None:
        lookup = "updated__gte" if parsed.updated_after_inclusive else "updated__gt"
        queryset = queryset.filter(**{lookup: parsed.updated_after})
    if parsed.created_after is not None:
        lookup = "created__gte" if parsed.created_after_inclusive else "created__gt"
        queryset = queryset.filter(**{lookup: parsed.created_after})

    if not parsed.wants_deleted:
        queryset = queryset.filter(published=True)
    elif not parsed.wants_ready:
        queryset = queryset.filter(published=False)
    return queryset
