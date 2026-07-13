"""``User``: a `Literal` of known Asana workspace handles once generated
(``python -m flex_asana.update_users``), for IDE autocomplete; plain ``str``
before that. flex-exp imports this (falling back to ``str`` if flex-asana
isn't installed at all) as the type hint for ``Experiment(user=...)``.
"""

try:
    from flex_asana._generated_users import User
except ImportError:
    User = str

__all__ = ["User"]
