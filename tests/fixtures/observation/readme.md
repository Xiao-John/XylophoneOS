# P1-A offline fixtures

These are synthetic, recorded observation/proposal pairs for the production
offline validator. They are not captures of a running guest. The test runner
checks their typed outcomes against `expected.json`; real endpoint observations
and guest results are qualified separately.

Each record contains the schema, validator and policy versions, explicit logical
time, a bounded observation, the proposal as actually recorded, and the policy
used by that evaluation. The policy is an evaluation input, not proof of current
OS authority. There is no model call or executor. The same recorded pair can be
evaluated by an ordinary CLI:

```sh
python3 scripts/observation_replay.py tests/fixtures/observation/self_inspect.json
python3 tests/observation_replay_test.py
```

The CLI emits one canonical JSON result. Exit 0 means `accepted_proposal`, exit 1
means a typed rejection, and exit 2 means malformed input. Every result denies
execution authority and automatic retry. Result hashes bind canonical input,
all three checked-in schemas, and the exact validator bytes. Changing a model's
output changes the recorded proposal input; no deterministic model generation
is assumed.

Version 1 accepts `inspect`, `diagnose` and `refresh_observation` as proposals.
An unknown or writing action remains recordable but evaluates as `unsupported`.
An unavailable source or missing bounded record cannot prove nonexistence.
Successful reads are independently sampled, scope-limited observations, never
a global atomic snapshot. The `self` and `direct_child` scopes refer to the
provider in `observation.source.pid`, whose native authority is used to capture
the data; `caller_pid` identifies the separately authorized consumer. Runtime
and trust owners are likewise the provider. Successful trust records use
`selection="loaded_snapshot"` for an owner-selected, ready, verified immutable
trust store. A configured pin alone is rejected as an active-trust record.
These synthetic fixtures exercise that schema distinction; they do not prove
that a store was loaded in a real process. Independent production-store tests
qualify the source adapter. A selected snapshot does not change existing TLS
stream anchors or establish TLS connectivity.
