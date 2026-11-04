# Midnight Dock review evidence

This derived selection retains Dock-specific scanouts, guest serial records and outcome reports. The original interactive report contains 11/11 checks; a later, separately built interactive run reported 10/10. Those results are tied to their original builds, not this rebased source. The original Studio attempt failed; the rerun passed and both records remain here. Pixel differences in six Dock regions are not an aesthetic assessment.

The original full evidence bundle and its historical hashes remain in source commit `bf279f26b41ec6713d958a0f137553695fc0f8d1`; this new flat selection omits duplicate non-Dock material. Current-base rebuilding and guest requalification are required before claiming a new result.

After rebuilding on main `72bfacb`, the previous Dock interactive run passed 11/11 checks, including the supplied legacy Qt application. The guest serial and runner records are retained alongside the results. This does not requalify every historical suite.

Round 2 rebuilt the system, Dock targets, and legacy Qt fixture on main
`48882c9`. Real QEMU passed 11/11 interactive checks, including the legacy
Qt lifecycle, exact resource restoration, display release and file sync.
See the [current result](round2_interactive.json) and its
[serial log](round2_interactive.serial.log.gz). The older Studio failure and
other historical suite results remain bound to their original inputs.
