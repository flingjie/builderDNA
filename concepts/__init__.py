"""Concept lifecycle — persistence, matching, scoring, and evidence adapters.

The canonical Pydantic contracts live in ``models/concept.py`` and
``models/radar_payload.py``. This package provides the deterministic logic that
operates on them: the concept store, candidate matching, experiment-priority
scoring, and source evidence adapters.
"""
