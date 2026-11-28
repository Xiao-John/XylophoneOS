# Public scope of the combined network qualification

This report records actual DHCP and TLS runs at source
`3699916df590a2fe0ea9b419836ded2d9344e6b3`. The explicit DHCP system passed
eight peer scenarios; the default static-network system and v3 glibc SDK passed
twenty TLS/trust-store scenarios. These identities describe those actual runs,
not a later source or SDK revision.

The directory publishes build/input receipts, ordinary guest receipts, serial
logs and aggregate conclusions. The DHCP capture contains 197 test frames:
73 DHCP, 76 ARP, 28 DNS and 20 application UDP frames. The local qualification
also matched ten independent peer challenges to guest output.

**The raw DHCP capture and its full frame/payload decode are retained only
locally. Neither is published here.** The local capture SHA-256 is
`ef40f835af3c515052e2d7d5066d38e3b2902cbbdfb7ec94c385371f85409557`.
This digest identifies the retained input; it does not make the packet data
available for public reinspection.

Automatic approval rejected the raw capture upload, including after a complete
read-only review of the controlled fixture provenance and packet contents,
because explicit permission to disclose the capture metadata was not
established. The candidate public tree therefore excludes both the binary and
the full decoded representation. It does not substitute another encoding or
publish equivalent frame/payload data. The detailed safety review also remains
local. This disclosure change does not alter the executed tests or their
recorded results.

`manifest.json` hashes only the files actually published in this directory.
`summary.json`, `dhcp_guest.json` and `verification.json` distinguish the local
capture check from the public evidence. The conversion record is outside the
report directory at `docs/evidence_exports/p0_network_combined_20261128.json`.
