"""Evidence adapters — normalize source data into immutable ``ConceptEvidence``.

Each adapter converts raw source records (Reddit RSS findings, GitHub repo/issue
signals, manually captured X posts) into ``models.concept.ConceptEvidence`` with
an explicit role, directness, strength, and ``independence_key``.
"""
