# Targeted SSG fixture after combined-run failure

An integration run of the original whole-tree fixture failed the
`ssg_incremental_change` assertion after the earlier checks passed. That run did
not print its two capped flags or diff status, so its precise cause is **unknown**.
It is preserved in `combined-failed`. A subsequent diagnostic build on the same
source combination passed and printed `first_capped=0 second_capped=0 delta=OK`;
that passing rerun does not explain the first failure. Its debug-only source and
raw serial output are retained in `combined-diagnostic-rerun`.

The fixture previously assumed the bounded whole-tree query was complete. The
updated fixture instead requests a `textbox`-scoped snapshot, asserts both
endpoints are uncapped and verifies that the exact real `draft-title` change is
present in the diff. This does not change the production 30 ms budget or relax
the requirement for a correct complete diff. On the SDK branch the updated
fixture passed all 26 native assertions and five guest gates with exact resource
return (`targeted-sdk`). A new combined-source run is still required; no result
from the diagnostic build substitutes for it.

Each guest report records the actual QEMU command and image/ELF SHA-256. The
target receipt records build commands and input hashes; `evidence.json` hashes
the fixture and preserved outputs. All runs use the existing frozen one-core,
512 MiB XOS image and dedicated synthetic disk.
