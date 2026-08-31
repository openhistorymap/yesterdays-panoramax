"""Stable, invertible UUIDs for federated objects.

The Panoramax meta-catalogue stores harvested identifiers in UUID columns --
``id UUID PRIMARY KEY GENERATED ALWAYS AS ((content ->> 'id')::UUID) STORED``
on both ``collections`` and ``items``, and ``collection_id UUID`` on items --
so a harvest of an instance that publishes integer identifiers aborts on the
first row. Yesterdays uses integer primary keys.

This app is meant to drop into an existing installation, so it cannot add a
UUID column to ``images.Image``. Serving ``/api/collections/<uuid>/items``
still needs to get from a UUID back to a primary key, and a hash is one-way,
so the identifier carries the key instead of pointing at a lookup table:

===========  =================================================================
bytes 0-8    digest of (namespace, kind), with the RFC 9562 version (8) and
             variant bits stamped over it
bytes 9-15   the primary key, 56-bit big-endian
===========  =================================================================

Version 8 is RFC 9562's "custom format", which is exactly this: an application
laying out the bits itself. Decoding reads the key out of the tail, then
recomputes the prefix for each known kind and keeps the one that matches, so a
UUID minted by another instance -- or under another namespace -- is rejected
rather than mistaken for one of ours.

The identifiers are a pure function of the namespace and the primary key. They
survive a rebuild of this app's tables, and they must stay stable: changing
``PANORAMAX_UUID_NAMESPACE`` re-publishes the entire catalogue under new
identifiers and orphans everything already harvested.
"""

import uuid
from hashlib import blake2b

from . import conf

COLLECTION = "collection"
IMAGE = "image"
KINDS = (COLLECTION, IMAGE)

_PREFIX_BYTES = 9
_KEY_BYTES = 16 - _PREFIX_BYTES
MAX_PK = (1 << (_KEY_BYTES * 8)) - 1


class InvalidFederatedId(ValueError):
    """Raised when a UUID was not minted by this instance."""


def _prefix(kind: str) -> bytes:
    """The nine leading bytes for *kind*, version and variant already stamped."""
    digest = bytearray(
        blake2b(
            f"{conf.uuid_namespace()}:{kind}".encode(),
            digest_size=_PREFIX_BYTES,
        ).digest()
    )
    # RFC 9562 puts the version in the high nibble of byte 6 and the variant in
    # the top two bits of byte 8. Both land inside the prefix, so stamping them
    # here keeps the digest and the key halves cleanly separated.
    digest[6] = 0x80 | (digest[6] & 0x0F)
    digest[8] = 0x80 | (digest[8] & 0x3F)
    return bytes(digest)


def prefix_bytes(kind: str) -> bytes:
    """The constant nine-byte prefix for *kind*.

    Exposed so that SQL which has to mint identifiers in the database -- the
    vector tiles -- can append a key to it rather than reimplementing the
    scheme in PL/pgSQL.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown federated kind: {kind!r}")
    return _prefix(kind)


def encode(kind: str, pk: int) -> uuid.UUID:
    """Build the federated UUID for *pk* of *kind*."""
    if kind not in KINDS:
        raise ValueError(f"unknown federated kind: {kind!r}")
    if not isinstance(pk, int) or isinstance(pk, bool):
        raise TypeError(f"primary key must be an int, got {type(pk).__name__}")
    if pk < 0 or pk > MAX_PK:
        raise ValueError(f"primary key {pk} is out of range for a federated id")
    return uuid.UUID(bytes=_prefix(kind) + pk.to_bytes(_KEY_BYTES, "big"))


def decode(value) -> tuple[str, int]:
    """Recover ``(kind, pk)`` from a federated UUID.

    Raises :class:`InvalidFederatedId` for anything this instance did not mint,
    which is what turns a stray or foreign identifier into a 404 rather than a
    lookup against an unrelated row.
    """
    if not isinstance(value, uuid.UUID):
        try:
            value = uuid.UUID(str(value))
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidFederatedId(f"not a UUID: {value!r}") from exc

    raw = value.bytes
    prefix, key = raw[:_PREFIX_BYTES], raw[_PREFIX_BYTES:]
    for kind in KINDS:
        if prefix == _prefix(kind):
            return kind, int.from_bytes(key, "big")
    raise InvalidFederatedId(f"{value} was not minted by this instance")


def decode_kind(value, expected: str) -> int:
    """Recover the primary key from *value*, requiring it to be *expected*."""
    kind, pk = decode(value)
    if kind != expected:
        raise InvalidFederatedId(f"{value} is a {kind} id, expected {expected}")
    return pk


def collection_uuid(pk: int) -> uuid.UUID:
    return encode(COLLECTION, pk)


def image_uuid(pk: int) -> uuid.UUID:
    return encode(IMAGE, pk)
