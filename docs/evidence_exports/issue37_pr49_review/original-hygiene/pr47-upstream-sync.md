# SSG P2 diagnostic draft: upstream synchronization

This branch integrates the P1 dependency `f2de11e1fb5fe2c96b7ff348bd415b6a67b225fb`. The instrumented Browser cross-built and passed seven small-fixture SSG guest checks on the reused QEMU image. Those checks do not establish completion or a valid diff for the large page: the original diagnostic retains its failed large-page observations and incomplete status. The latest full P1 run on the dependency failed at a denied-consumer exit; a focused retry passed, but the cause remains unresolved.

The original and sanitized diagnostic indexes each verify 10/10 entries. The exported archive contains 56 members; one member contains path-only substitutions and the other 55 retain their original bytes. Archive owner names are redacted. The source commit and hashes are in `pr47-lineage.json`; historical command templates need manual configuration and no portable replay is claimed. Dependencies remain unmerged.
