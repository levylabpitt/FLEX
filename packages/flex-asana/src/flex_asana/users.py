"""``User``: a Literal of the Asana workspace handles for ``Experiment(user=...)`` autocomplete,
once ``python -m flex_asana.update_users`` has generated it; plain ``str`` before that."""

try:
    from flex_asana._generated_users import User
except ImportError:
    User = str
