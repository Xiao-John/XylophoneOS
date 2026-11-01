# Temporal Semantic Stream — proposal and host-only synthetic model

2026-10-30. **PROPOSED / NOT A SYSTEM ABI / NOT A VIDEO PLAYER.** This document
describes a future user-space source of time-indexed observations for an
authorized consumer. `experiments/temporal_semantics/mock_producer.py` is a
deterministic host experiment with synthetic bytes. It does not decode video,
capture audio, run a vision model, implement IPC, enforce security isolation or
demonstrate LocalPilot integration. No syscall or wire number is allocated.

## Observation model

All content and model output are untrusted data. A production protocol must
authenticate the source and bind a separately authorized lease to the source
instance, consumer, operation, sensitivity, expiry, quotas and revocation epoch.
A model proposal or a returned frame reference never creates that lease.

| Record | Source and minimum meaning | Explicit limits |
|---|---|---|
| Stream | Source instance, session/epoch, version, provenance, access state and quotas | New producer/reload gets a fresh authenticated instance; PID alone is insufficient |
| Playback state | Playing/paused/buffering/ended/unknown and a media position | Measured by the producer; no extrapolation across pause, seek or source change unless specified |
| Caption cue | Text, language when known, media start/end and track identity | Producer-supplied; may be missing, inaccurate, protected or outside permitted scope |
| Frame reference | Source epoch, opaque frame ID, presentation time, format/size and lifetime | Request on demand; bytes or pixels only after separate frame-read authorization |
| Audio track | Track identity, format/rate when known, access status | Track metadata does not grant access to samples; the mock provides no samples |
| Observation event | Version/sequence, type, provenance, bounded payload and observed time | Version gaps, dropped data and unavailable history require resync, not inferred continuity |
| Model inference | Model/version, input references, generation time, uncertainty and output | Separate from producer fact; absent analysis is `NOT_RUN`, never a fabricated description |

Status must distinguish `DENIED`, `PROTECTED`, `UNAVAILABLE`, `UNKNOWN`,
`RESOURCE_LIMIT` and source replacement; absence of a field is not evidence
that content or an event does not exist. Results should identify whether a list
or time interval is complete. A frame can be present without a semantic
description; a caption is not a verified account of the picture.

## Clocks and access

The **media timeline** and the **system monotonic observation/deadline clock**
are different domains under C29. Caption and frame presentation timestamps are
media-domain values. Consent expiry, capture observation, waits and resource
leases use the system's monotonic domain. A mapping, if any, is explicitly
sampled and invalidated on seek, rate change, buffering, pause or discontinuity;
raw values from different domains cannot be directly compared. The mock uses a
caller-supplied *simulated* observation clock and never claims it is XOS time.

On-demand access may select a permitted time, key frame or change event and must
use bounded requests, lifetime and quota. Future change detection and model
inference are distinct optional consumers; this proposal requires neither
periodic screenshot capture nor inference on every frame. Image handles must not
silently expose a process's screen or another origin's data. Production media
buffers need an independently reviewed ownership/copy/revocation contract;
this document assigns no shared-memory right.

On revocation, expiry, producer exit or source replacement, old permits and
references fail. If a consumer cannot tell whether an external effect occurred,
it remains `UNKNOWN` and is not automatically replayed. Authorized media access,
semantic observation and action authority are separate policies; protected or
cross-origin content remains subject to the owning trusted service's policy.

## Experiment and acceptance boundary

The small mock demonstrates scoped metadata/caption access, explicit simulated
time domains, on-demand synthetic byte references, a frame quota and rejection
after expiry, revocation or source replacement. The `TestPermit` object is
deliberately mutable and exists solely inside one host process; it is not a
security mechanism. Run `python3 tests/temporal_semantic_model_test.py`.

Before any production claim: demonstrate a real native player and decoder,
authentic provider discovery, user-facing permission decisions, bounded copying,
disconnect/revocation races, seek/pause timing against actual media timestamps,
protected tracks, audio policy, event loss and resource limits on real XOS.
Frame interpretation additionally needs an actual model and separately recorded
inputs/provenance; no such test has run here.
