"""Custom template filters for the core app."""

from __future__ import annotations

from django import template

register = template.Library()

# New filter to access a dictionary value by key in templates
@register.filter
def get(value, key):
    """Return the value of ``value[key]`` for dictionaries in templates.

    Usage::

        {{ mydict|get:var }}

    This helper tries to return ``value[key]`` if ``value`` implements
    ``dict.get``.  It is useful in templates where accessing a
    dictionary by a variable key (e.g., ``row[col]``) is not allowed by
    the Django template engine.  If the key does not exist or an
    exception occurs, an empty string is returned.

    Args:
        value: A dictionary-like object.
        key: The key to retrieve.

    Returns:
        The value for the given key or an empty string if not found.
    """
    try:
        if hasattr(value, 'get'):
            return value.get(key, '')
        return ''
    except Exception:
        return ''


@register.filter
def attr(obj, attr_name: str):
    """Retrieve an attribute from an object dynamically in templates.

    Usage in a Django template:

    .. code-block:: django

        {{ myobject|attr:"field_name" }}

    This filter will attempt to get the attribute named ``field_name`` from
    ``myobject`` and return its value. If the attribute does not exist,
    ``None`` is returned instead of raising an exception.

    Args:
        obj: The object from which to retrieve the attribute.
        attr_name: Name of the attribute to retrieve.

    Returns:
        The value of the requested attribute or ``None`` if it does not
        exist.
    """
    return getattr(obj, attr_name, None)

@register.filter
def startswith(value, arg: str) -> bool:
    """Return True if the given string starts with the specified prefix.

    This filter mirrors Python's ``str.startswith`` method for use in
    templates. It is useful when template logic needs to conditionally
    include content based on the beginning of a string, such as field
    names or identifiers.

    Args:
        value: The string to test.
        arg: The prefix to look for.

    Returns:
        A boolean indicating whether ``value`` begins with ``arg``.
    """
    if value is None:
        return False
    return str(value).startswith(str(arg))

# Custom tag to render active panel labels for a membership
@register.simple_tag
def panel_names(membership, panel_labels) -> str:
    """Return a comma-separated list of panel labels enabled for a membership.

    This helper iterates over ``panel_labels`` (mapping of field name to human
    readable label) and includes those labels where the corresponding
    membership attribute is truthy.  Usage in template:

    .. code-block:: django

        {% load custom_tags %}
        {% panel_names membership panel_labels as names %}
        {{ names }}

    Args:
        membership: A Membership instance.
        panel_labels: Dict mapping membership field names to display labels.

    Returns:
        A string containing enabled panel labels separated by commas.
    """
    try:
        labels = [label for field, label in panel_labels.items() if getattr(membership, field)]
        return ', '.join(labels)
    except Exception:
        return ''