# 0109 — Temporal semantic stream proposal

2026-10-30, independent branch at upstream `3377dbf`. Added a reviewable
user-space data model, a host-only synthetic producer and five host unit tests.
Media presentation time and simulated monotonic observation time are explicitly
different domains. Caption scope, on-demand synthetic frame references, quota,
expiry/revocation and source replacement are tested; inferred descriptions are
`NOT_RUN`. The mutable test permit is not a security boundary.

Run `python3 tests/temporal_semantic_model_test.py -v`. The five tests passed on
the host; no XOS target build or real media was run. See
[the proposal](../contracts/temporal_semantic_stream_proposal.md) for the data
model, failure states and production acceptance gaps. No kernel, ABI, device
driver or LocalPilot installation is modified. Next review the model, then use
an actual player/decoder, authenticated source and permission service before
claiming video or audio observation; model inference is a separate test.
