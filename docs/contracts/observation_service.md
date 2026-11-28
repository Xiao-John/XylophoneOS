<!-- SPDX-License-Identifier: Apache-2.0 -->
# P1-A read-only observation service and proposal replay

P1-A supplies an optional, embeddable user-space observation endpoint and an
offline proposal validator. An ordinary native client can use both without a
model. The endpoint has one wire operation, `read`; the validator never executes
an action. This implements the observation/proposal boundary in the
[P1 plan](../plans/p0_completion.md), not the separate persistent authority,
recovery or autonomous-writing workstreams. It does not close remaining P0
qualification or publication gates.

The kernel source is specified separately by
[native observation v1](native_observation.md). The service ABI is
[`observation_service_abi.hpp`](../../src/shared/include/xos/observation_service_abi.hpp),
the public API is [`observation.hpp`](../../src/user/include/xos/observation.hpp),
and the production source adapter is
[`observation_sources.hpp`](../../src/user/include/xos/observation_sources.hpp).
An application links the matching source-built SDK and runs on the matching
sys90-capable kernel. The endpoint is not a default installed inventory daemon.

Transport uses sys84 generic IPC endpoints, including the same endpoint type
created by sys86 named connections, with sys84 peer/close and sys85 deadline
wait operations. It does not accept sys81 `generic_channel` transport: the
required `query_peer` check rejects that different channel type. The native
sys90 service **source** can separately observe an already-held sys81 endpoint;
that source compatibility does not extend the observation transport profile.

## Ownership and admission

A single owner serializes `initialize`, `attach`, `authorize`, `poll`, `revoke`,
`forget` and `close`. These are in-process owner operations, not remote wire
commands. The owner also controls source selection, service-name publication,
connection acceptance and distribution of the trusted server identity.

`initialize` assigns a nonzero random server epoch and records the owner's PID.
The epoch identifies this endpoint instance; it is not the process's native
image generation. A client receives the expected PID and epoch from its trusted
supervisor or deployment configuration. A discoverable name, a request body,
an observation file or a model response cannot supply that authority.

Admission has an explicit order:

1. The owner accepts a sys86 named connection, or supplies an authorized sys84
   generic IPC channel, under its existing native authority.
2. `attach` authenticates both endpoint directions to the same peer PID and
   uses sys90 on the held endpoint to capture the peer's image generation.
   Ownership of the channel transfers only on success; the owner must close
   both endpoints if attachment fails.
3. The owner calls `authorize(peer_pid, kinds, reads, expires_ns)`. An attached,
   still-authenticated peer is required. The grant binds its PID and image
   generation, a nonempty kind mask, a finite read budget and an absolute
   expiration. Attachment alone grants no reads.
4. The client issues bounded reads while the owner calls `poll`.

The grant is checked before capture. A successful pending reply is checked
again immediately before sending, including the grant revision. A same-PID
exec cannot use a grant from the previous image; reconnecting does not refresh
it. Supported sys84/86 endpoints are revoked by successful exec; no supported
transport route inherits the old grant across exec. Reauthorization is an
explicit owner decision and creates a new revision.

`revoke(pid)` retains the grant entry with a revoked state so subsequent reads
can report `revoked`. A captured success still waiting for mailbox space is
stripped of its data if the grant was revoked or changed. A reply already
queued before revocation is a historical authorized read; revocation cannot
erase a copy already delivered to the client.

`forget(pid)` closes all attached channels for that peer and releases its grant
slot, including expired or revoked grants. A missing peer returns
`unauthorized`; a zero PID or an uninitialized server returns `invalid`.
This explicit operation permits the owner to admit a later
consumer without restarting unrelated consumers. `close` retires all owned
channels and grants. No grant is persisted across an endpoint restart.

## Wire and correlation

Version 1 uses a fixed 64-byte request and 208-byte response. There is no
variable payload, path, address, command string or transferable grant field.
Unused data words, digest bytes and reserved fields must be zero.

| Request field | Contract |
| --- | --- |
| `version`, `size` | Exactly `1` and `64` |
| `operation`, `subject` | `read=1` and one of the six registered kinds |
| `sequence` | Nonzero, strictly consecutive on that connection |
| `deadline_ns` | Finite absolute monotonic deadline, at most five seconds ahead |
| `server_epoch` | The client's independently trusted endpoint incarnation |
| `expected_object`, `expected_generation` | Zero requests the current authorized sample; nonzero values are exact post-capture preconditions |
| `reserved` | Zero |

The response carries the request sequence and kind, a monotonically increasing
server-local observation ID, server PID/epoch, authenticated caller PID,
observation start and validity deadline, outcome, scope, object identity,
generation and typed data. A failure clears object identity, generation and
data. It must not disclose the previously successful sample.

The client checks length, version, reserved fields, all per-kind data rules,
sequence, source identity, caller identity, time bounds and the expected
incarnation. A server restart producing an explicit `stale` reply retires the
old client connection. A malformed reply returns `invalid` and closes the
connection. A transport failure or local expired deadline may return a typed
status with an empty `response`; the caller must not invent an observation
envelope for that case. Only `valid_response` results may be passed to
`print_json`.

## Provider scopes and data

The native authority belongs to the **provider**, identified by
`source.pid` / `server_pid`. `self` means that provider; `direct_child` means
its directly owned child. `caller_pid` identifies the independently authorized
consumer and is not substituted into the native lookup. Sources are explicitly
configured by the owner, not chosen by an untrusted request PID.

Each read captures one kind and produces one independent sample. Combining
six results does not create a global atomic snapshot. No generation value is a
reservation or proof that the state still holds after its validity interval.

| Kind | Scope and source | Object identity and generation | Exposed data and retained boundary |
| --- | --- | --- | --- |
| `process` (1) | `self` or `direct_child`; sys90 | PID and image generation | Parent PID, thread-aware state and allocated thread count, bounded by 64 in this wire profile. No unrelated-process enumeration. |
| `service` (2) | `held_endpoint`; sys90 on the provider's existing generic endpoint | Held endpoint token and peer image generation | Peer PID, observation metadata revision `1`, and `available`. This is endpoint liveness, not application health or the target service's protocol version. |
| `resource` (3) | `self` or `direct_child`; sys90 | PID and image generation | Owner/parent PID, owned generic IPC pair count and limit `4`, published-name count and limit `2`. The JSON field `endpoints_used` counts canonical pairs, not each direction. No tree budget or global resource inventory. |
| `runtime` (4) | `controller`; actual `activation_catalog::capture` | Active root ID and catalog sequence | Controller PID and the root digest. This catalog is local to one controller and volatile; the result establishes no persistent provisioning or global deployment state. |
| `network` (5) | `service`; authenticated Net2 session's `configuration` | Session's authenticated service PID and configuration epoch | `disabled`, `static_direct` or `dhcp`, plus `unconfigured` or `ready`. `ready` describes a selected address/configuration, not peer reachability or new network authority. The PID comes from the real session, not a separate caller-supplied label. |
| `trust` (6) | `application`; owner-selected ready, verified immutable trust snapshot | Loaded snapshot generation in both identity and generation fields | Provider PID, nonzero complete-snapshot digest and `selection="loaded_snapshot"`. A configured pin alone is not a successful active-trust observation. The record does not change existing TLS streams or establish TLS connectivity. |

Runtime and trust digests must be nonzero. Successful records require nonzero
identities and generations. Missing sources return `unavailable`; a missing
bounded record or failed read never proves that an object does not exist.
Native `denied` maps to `unauthorized`, and native copyout exhaustion maps to
`quota`. Other service-source failures retain typed outcomes rather than being
replaced with an empty successful snapshot.

The trust adapter uses a `trust_capture_fn` callback on an owner-selected
context. The supplied native TLS bridge accepts an actual
`native_tls::trust_store` only after it is ready: the store's load operation
must already have verified the independently selected generation/digest and
the complete bounded CA set. It copies the loaded generation and full-snapshot
digest into the observation. An absent context, an unready store or a failed
initial load cannot produce an `ok` active-trust record. Merely labelling a
configuration pin as active is not this contract.

The owner keeps that store alive and serializes selection, capture and
destruction. The record identifies the store selected for observation by that
owner, not a global default. As specified by the
[TLS trust-store contract](tls_trust_store.md), streams copy their anchors at
connection setup. Observing a newer ready store does not switch or revoke
existing streams, and it performs no TLS handshake or network transaction.

## Budgets, deadlines and scheduling

| Limit | Version 1 value and behavior |
| --- | --- |
| Attached connections | Four per server; a fifth returns `quota` |
| Grant entries | Four; `forget` releases entries explicitly |
| Capture allowance | One through 64 reads per grant; charged before invoking capture, including a failed capture or later precondition mismatch |
| Grant duration | At most 30 seconds from authorization, with a finite absolute expiration |
| Request interval | At most five seconds, shared by send wait, source capture and reply receipt |
| Per-connection buffering | One pending reply; full mailbox preserves it only until its deadline |

`poll` considers at most one request per attached connection and never waits
for an idle client. Captures are synchronous and serialized: a slow network
capture can consume the remaining request interval before later consumers are
visited. For the supplied adapters, one capture is bounded by the caller's
remaining interval, never more than five seconds. A full four-client pass can
therefore spend up to four such intervals plus processing/scheduling overhead;
this is not a hard real-time or immediate-return guarantee.

The owner must supply a capture callback that respects the supplied deadline.
The service checks time after return and discards late results, but cannot
preempt an arbitrary callback that never returns. The provided native sources
perform bounded scans; the Net2 adapter passes the same absolute deadline into
the authenticated session. There is no per-attempt deadline reset.

The client waits through native absolute-deadline IPC operations. Once a request
has entered its send/receive loop, expiration or channel failure closes the
affected connection; late replies cannot be adopted as a later request's result.
A deadline already expired before sending returns `deadline` without consuming
a sequence or closing an otherwise valid connection. The API performs no automatic reconnect or second
capture after an unknown transport outcome. An owner or consumer may reconcile
identity and deliberately start a new read with a new deadline.

| Status | Wire value | Meaning |
| --- | ---: | --- |
| `ok` | 0 | Valid, authorized sample |
| `invalid` | 1 | Malformed request/reply, unsupported framing, or invalid local API use |
| `unauthorized` | 2 | Missing kind grant, changed caller incarnation, or denied native source |
| `stale` | 3 | Endpoint incarnation, exact object/generation, expiration or pending grant revision no longer matches |
| `revoked` | 4 | Explicitly revoked grant or retired/broken transport |
| `deadline` | 5 | The absolute deadline was reached |
| `quota` | 6 | Connection/grant/read capacity or source resources exhausted |
| `unavailable` | 7 | A selected source cannot supply a valid sample |
| `unsupported` | 8 | The selected source does not implement the requested capability |

## JSON and offline proposals

`print_json` writes one bounded JSON observation using the
[observation schema](../schemas/observation_v1.schema.json). A successful
native reply has one record. A valid failure envelope has `records=[]` and its
typed failure status. The schema additionally accepts bounded recorded
collections, but collecting records is not an atomic-snapshot operation.

The separate [proposal schema](../schemas/proposal_v1.schema.json) records a
proposal ID, caller, source incarnation, observation ID, exact target identity
and generation, action name and expiration. No command payload, execution
token or capability is accepted. Version 1 validates `inspect`, `diagnose` and
`refresh_observation` as proposals; other action names return `unsupported`.

The [replay schema](../schemas/observation_replay_v1.schema.json) contains the
observation/proposal pair, schema/validator/policy versions, explicit logical
time and recorded policy. Policy names the consuming PID, allowed kinds/objects,
scopes/actions and maximum observation age. It is an evaluation input, never
evidence of current OS authorization.

[`observation_replay.py`](../../scripts/observation_replay.py) uses those inputs
only. It does not read wall-clock time, invoke a model, contact an endpoint or
execute an action. Every verdict includes `execution_authority=false` and
`automatic_retry=false`. `accepted_proposal` means the recorded pair satisfies
the recorded validation policy; it grants no authority to run the proposal.
Unknown sources and failures retain their typed outcomes and do not become
negative existence assertions.

Replay input is limited to 65,536 UTF-8 bytes, 12 nested containers and 32
records. Duplicate keys, floating/nonfinite numbers, extra fields, invalid
identities, scope mismatches and unbounded validity are rejected. Results bind
the canonical input hash, three exact schema files and validator bytes. Same
recorded inputs and validator/schema bytes produce the same result. Model
output is preserved as input; model generation itself is not assumed to be
deterministic.

## Compatibility and qualification

The endpoint version does not alter existing IPC wire formats. Its service name
is owner-selected, and PID/epoch must be distributed through an already trusted
configuration or control path. There is no fallback to an older kernel's
unscoped statistics or to a natural-language command. A rollback may disable
this optional consumer without adding a model to the OS release dependencies.

The [usage guide](../usage/userland/observation.md) shows ordinary client,
provider and replay entry points. Native-source host tests substitute privileged
copyout/clock boundaries; transport host tests substitute the kernel transport;
offline replay fixtures are synthetic. These scopes are distinct from execution
in a matching QEMU guest or an installed release. Actual guest configurations,
commands, pass/fail results and image/SDK identities belong to the P1-A delivery
record; the existence of this contract or a host pass does not establish them.
The ordinary guest runner records an absent network or trust source as typed
`unavailable`; its separate `--network` mode observes a live static Net2
configuration. Active-trust source qualification is a separate regression
against a real ready, verified immutable store; its execution environment and
results must be recorded independently. The ordinary/network profiles do not
establish DHCP lease-transition observation, runtime ELF loading, CA-bundle
loading, fork-generation guest behavior, model generation, autonomous writes
or default installed-profile qualification.
