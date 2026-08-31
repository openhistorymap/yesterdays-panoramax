"""Access to the host application's models, by app label.

This package is a plugin. It requires an installed app whose Django **label**
is ``images``, providing the models described in ``docs/host-contract.md`` --
but it must not assume where that app sits on the Python path. In a Yesterdays
deployment the app is the top-level ``images``; in this repository's own test
harness it is ``tests.images``; a project that vendors Yesterdays under a
namespace package would have it somewhere else again. All three have the label
``images``, which is what the app registry, the ``OneToOneField("images.Collection")``
reference and the migration dependency already key on.

Resolution is deferred to attribute access (PEP 562) rather than done at import
time, because this module is imported while the app registry is still being
populated -- ``models.py`` pulls it in during ``import_models()``, long before
``images`` is ready. Touch an attribute only from inside a function, a method,
or ``AppConfig.ready()``.

    from . import hostmodels

    hostmodels.Image.objects.filter(...)   # fine inside a function
    SENDER = hostmodels.Image              # NOT fine at module level
"""

from django.apps import apps

HOST_LABEL = "images"

_MODELS = frozenset({"Collection", "Georeference", "Image", "License", "Source"})


def __getattr__(name):
    if name in _MODELS:
        return apps.get_model(HOST_LABEL, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(_MODELS | {"HOST_LABEL"})
