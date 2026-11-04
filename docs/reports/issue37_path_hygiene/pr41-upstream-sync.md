# Desktop draft: current upstream synchronization

The branch integrates the SSG dependency at `39a4ede579489376291d4cb08f49d70d5f163f81`, which includes upstream main `0a91a2bb1eabd6977f1001ac8bd7781a88fae225`. The already-built Desktop/session binaries were exercised with the newly built Browser and prior Notes binary on the reused QEMU image. All five session handoff, exit and resource checks passed. This is a scoped integration check, not a new full desktop or distribution qualification.

The original frozen evidence index and the separately labeled sanitized export each still verify 260/260 entries; see the lineage record in this directory. The source dependency remains unmerged into main.
