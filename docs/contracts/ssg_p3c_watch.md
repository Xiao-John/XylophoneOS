# SSG P3C: bounded, prewired observation

This user-space prototype extends the two prewired P3B provider routes. It is
not a broker, a permission grant, an application-discovery service or a desktop
snapshot. The trusted supervisor assigns each slot and random source instance;
provider fields are consistency checks, not authority. Browser and Notes use
their existing protocols, and the watch state machine depends only on
`provider_adapter`, `observation` and `comparison` in `provider_contract.hpp`;
`watch_service.hpp` schedules those interfaces without application-specific
types. Adapter-owned bounded payloads are opaque to the state machine.

Each observation reports the slot, source instance, epoch and revision, scope,
presentation, capabilities, monotonic start/end, completeness, freshness and
failure. The event includes those fields, the previous and new revision, a
source-qualified namespace object (slot, instance and epoch), a source-local sequence and a bounded change summary.
The capability set describes what the *adapter* can establish; `SCOPED`,
`LIMITED`, `UNSUPPORTED` and `UNKNOWN` must not be upgraded to universal access.
Source revision is not a timestamp, identity or authorization. A complete
source is still `UNVERIFIED_AFTER_OBSERVATION`, and the two observations and
liveness checks are sequential: `globalAtomicSnapshot=NOT_IMPLEMENTED`.
An empty event epoch or revision means that value is unknown or unavailable;
it is not revision zero and must not be interpreted as an observed identity.
The scope records the adapter's attempted collection, not a grant; denial and
protection still yield no current payload even when that scope is named.

The Browser adapter reuses its paged collector and existing Browser baseline
diff. It returns a reset when node continuity cannot be established, and does
not claim complete geometry when fragments are incomplete. The Notes adapter
reuses the revision-consistent UTF-16 range transaction; a reset, refusal or
failure discards staged text. Its events contain text-change and length facts,
not document contents. A capped Notes snapshot can be retried at most twice
within the same source deadline; each attempt is a fresh transaction, the
retry count is reported, and persistent capping remains unknown rather than
becoming a complete baseline. For this Notes adapter, the event's `retry_count`
counts capped snapshot retries, not the separate revision-reset attempts within
a text-range transaction. Unsupported geometry is explicit. The previous payload
is released on denial, protection, invalidation or unavailability. Previously
delivered authorized data is historical and cannot be retroactively erased.

## Execution and bounds

`ssg-multi ... --watch` performs sequential pulls with at most one request in
flight per source. `--watch-interval` accepts 1–30 seconds, `--watch-duration`
1–3600 seconds, `--watch-cycles` 1–1024 and `--watch-timeout` 1–300 seconds.
Defaults are 5, 120, 12 and 60 respectively. Each transaction receives an
independent wire-time budget bounded by the remaining duration; each wire operation is
also limited to 30 seconds. Duration is checked between transactions; parsing,
output and shutdown can make observed wall time longer, so this is not a hard
real-time deadline. A terminal wire error is not retried on a possibly
misaligned stream. A failed source does not prevent another source from being
sampled. Existing P3B paging, transaction and aggregate size bounds still apply.
Only the prior and in-progress bounded payloads are retained for each source;
there is no growing history.

Events are written synchronously as length- and sequence-checked base64 frame
records. Each record is at most 256 bytes and uses one console syscall; the
decoder must reject missing, duplicated, malformed or incomplete records and
require a new baseline after a gap. This framing addresses interleaved console
logs on the tested single-CPU guest; the shared console does not authenticate
which process wrote a record, and framing alone cannot detect every same-length
corruption. There is **no event queue**, so
there is no queue to overflow or silently discard from. An output failure ends
the stream, marks delivery `UNKNOWN` and requires a reset; a failed output
channel cannot be relied on to deliver even that final marker. There is no
durable acknowledgement or replay. The successful `dropped=0` counter means no
local event queue discarded an event; it is not downstream delivery proof. A new full observation is required after a
gap. The polling model can miss intermediate edits between observations, even
when both endpoint snapshots are complete. Detection latency depends on the
poll interval and the time to observe both sources.
The stop record's `elapsed_ns` covers the observation loop, not the subsequent
worker joins or child shutdown; full session wall time is measured separately.

For each event, the console records are `P3C_EVENT_BEGIN <stream_sequence>
<payload_bytes> <base64_bytes>`, followed by one or more `P3C_EVENT_PART
<stream_sequence> <encoded_offset> <base64_chunk>` records and a
`P3C_EVENT_END <stream_sequence>` record. The stream sequence starts at one for
each watch and is distinct from the source-local sequence inside the JSON.
Payloads are at most 8,192 bytes; chunks contain at most 96 base64 characters.
Other console records may appear between parts. Missing parts, wrong lengths,
duplicates, or sequence gaps are a broken stream, not an unchanged source.

The current event sink requires a console-backed standard output. A redirected
pipe or file is rejected before starting the watch because the current libc
pipe writer can wait without a deadline; there is no bounded subscriber pipe
or replay service yet. This restriction is part of the prototype, not a claim
that a console is a production event transport.

An explicit stop may be sent by a trusted caller that has prewired a read pipe
to the supervisor's standard input and supplied `--watch-control-stdin`:
the byte `S` or EOF requests cancellation. The cancellation worker uses the
existing pipe and thread APIs, cancels outstanding transfers cooperatively, and
is joined before the source channels are closed. The ordinary shell's console
is not such a pipe; this is not an interactive shell stop command. The finite
cycle and duration bounds also stop a watch. A stop or deadline during an
incomplete pair marks the final aggregate partial. A source can exit and its peer can
continue, but the current supervisor does not reconnect or transparently restart
providers. A future trusted rewire must assign a new source instance and acquire
a new baseline; `watch_slot::rewire` only supplies the state-machine operation,
not a restart service.

`SOURCE_CHANGED`, `SOURCE_UNCHANGED`, `SOURCE_REPLACED`, `SOURCE_INVALIDATED`,
`PERMISSION_CHANGED`, `SOURCE_UNAVAILABLE`, `SOURCE_UNKNOWN` and
`RESET_REQUIRED` are source-local classifications, not a continuous event log
from the underlying application. An initial baseline is `SOURCE_UNKNOWN` with
`INITIAL_BASELINE`: the prior state was not observed. A restriction or source
failure is never recast as unchanged. `SOURCE_UNCHANGED` covers only the
adapter's supported and successfully compared fields; it does not assert that
an unobserved field or the source's own revision did not change. A newly acquired baseline after an
unavailable, invalid or unknown comparison emits `RESET_REQUIRED`; a new epoch or
trusted source instance emits `SOURCE_REPLACED` before any ordinary diff.

Normal builds print event metadata and bounded summaries only. Test-only
executables can capture raw synthetic IPC and owner data for an independent
verifier. Those diagnostics are not a general authorization path and must not be
used with real user documents. The single-Surface environment keeps the other
real provider hidden and without input; it does not prove two visible windows
or background input.
