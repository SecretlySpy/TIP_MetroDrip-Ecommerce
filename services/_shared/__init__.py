"""Cross-cutting helpers shared by the strangler sidecars.

Nothing here may import Django, SQLAlchemy, or another service — these modules
run inside every sidecar image and must stay dependency-light.
"""
