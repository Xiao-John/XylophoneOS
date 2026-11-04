> Historical guest result: this was recorded on the earlier branch, before the current naming changes.

# P2 diagnostic branch: watchdog synchronization

The branch now uses the existing native-join watchdog implementation from
commit `c9ff0bce050a6777b5f1777c714f9443a23e3ee4`, which later SSG branches
already contain. The Browser was rebuilt from this branch and its real-guest
geometry, navigation, visibility, rejected Canvas and resource-return test
passed 7/7 checks. This is a small-fixture Browser result; it does not qualify
the known large-page pagination failure or prove that all exit races are fixed.
The corresponding guest serial output is `browser-guest.serial.log.gz`.

The current rebased diagnostic Browser also passed 7/7 small-fixture guest checks; the serial and runner records are included. The large-page result remains FAILED or capped.
