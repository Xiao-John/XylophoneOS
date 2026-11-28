# P1-A scoped observation qualification

This directory records new P1-A runs on the source and artifacts identified in
`qualification.json` and `source_bindings.json`. Ordinary native clients use
the real kernel and user-space endpoint without a model. Static Net2 and the
real loaded-trust source are separate named configurations.

The trust guest runs real CA parsing, the ready-store bridge, production source
capture and production JSON output. It uses a matching signed-source glibc SDK
and newly compiled adapter objects. It does not claim a second remote IPC grant
test or a TLS handshake. Those boundaries are retained in the individual reports.

Each `*_replays.json` retains the actual recorded observation, an explicit
ordinary inspect proposal, policy/version/logical-time inputs and the validator
result. The runner evaluates each pair twice and requires identical canonical
results. Results never grant execution authority or automatic retry. Host
synthetic fixtures are reported separately.

Reports are derived public exports. `provenance.json` identifies the original
new-run reports and records omitted host invocation fields. Guest serial logs
use lossless gzip; decompression restores the original bytes. Earlier failed work remains failed in
`development_failures.json`; later passing runs have different bound artifacts.
This evidence does not close P0 or qualify the unrun scopes listed in the report.

The version-1 flat `manifest.json` covers every other file in this directory.
Verify it from the repository root with:

```sh
python3 scripts/verify_evidence_index.py docs/reports/p1_a_observation_20261128/manifest.json
```
