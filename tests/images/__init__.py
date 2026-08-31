"""A stand-in for the Yesterdays ``images`` app.

This package is **not** shipped -- it exists so the adapter can be tested
without installing the whole Yesterdays project (PostGIS, pgvector, Celery,
RabbitMQ, Memgraph, a CLIP service). It reproduces exactly the models, fields
and behaviours the adapter reads, and nothing else.

That makes it the executable statement of the host contract: if a change to
Yesterdays breaks the adapter, the honest fix is to update this stub first and
watch the suite go red. See ``docs/host-contract.md``.
"""
