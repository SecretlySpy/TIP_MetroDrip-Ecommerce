"""Shared request/response schemas for the strangler seams.

One definition per message, imported by both sides of every seam:

- the FastAPI sidecars in `services/` declare these as their body and
  `response_model` types, so a service cannot drift from the schema;
- the Django provider adapters in `apps/*/providers/http.py` validate against
  the same models before posting and after receiving, so a client cannot drift
  either.

This package exists because the previous "contract tests" asserted the client's
outgoing shape against a mock and the server's shape against a `TestClient`,
with nothing connecting the two. Renaming a field on the server left the client
test green while every real call failed — the tests proved each side
self-consistent and said nothing about whether they agreed.
"""
