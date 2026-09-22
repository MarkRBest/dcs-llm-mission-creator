"""Mission scripts, grouped into terrain packages.

Each concrete module exposes one :class:`MissionBuilder` subclass.  The CLI
discovers modules recursively, while their public mission slugs remain
independent of this filesystem layout.
"""
