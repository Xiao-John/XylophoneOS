# 0209 — XYPm SDK host backend bundling and cache-stable profile

## Scope

P0 of the blind-test XYPm correction: make the packaged SDK self-contained for
`xypm install/upgrade/remove` and make XYPm use not invalidate the SDK profile.
No profile-design change (P1) and no asset replacement were performed.

## Problem

The published SDK lacked `tools/xypm_image.py`; a rebuilt SDK included it but not
the host FatFs backend sources it compiles on first use.  The host-tool cache was
written under `SDK/.cache`, while `xos_app` hashes the SDK tree; importing the
tools also creates `__pycache__` there.  Either action changed the profile-bound
tree hash and produced `SDK snapshot not registered for profile`.

## Changes

- `scripts/package_release.py`: `stage_dev_kit()` copies
  `scripts/xypm_disk_host.cpp`, `src/user/services/fatfs_unicode.cpp`,
  `src/third_party/fatfs/ff.c` and `src/third_party/fatfs/*.h` into the SDK with
  their original relative paths.
- `scripts/xypm_image.py`: compile cache moved to a per-user temporary directory,
  outside the SDK.
- `scripts/xos_app.py`: `tree_receipt()` ignores `__pycache__`, `*.pyc`, and
  top-level `.cache`; these are generated state, not SDK inputs.
- `scripts/sdk_receipt.py`: same generated-state exclusion in the release SDK
  tree receipt, so `verify_packaged_sdk` remains stable after a host-tool build.
- `scripts/release_smoke.py`: added `sdk_devkit_tools_and_xypm_host_backend` gate:
  required tools and backend sources exist, `xypm_image` imports and builds the
  host tool outside the SDK, and the packaged tree hash is unchanged.  Also added
  `sdk_xypm_install_query_remove`: a generated probe XPK is installed, queried and
  removed on a copy of the release work disk using the b2 profile.
- `docs/releases/SDK_DEVELOPING.md`: documented the host `clang++`/`c++`
  requirement for the offline transaction backend.

## Evidence

Workspace: `build/xypm_blind_investigation/`, `build/xypm_p0/`.

- released SDK: `ModuleNotFoundError: xypm_image`;
- rebuilt SDK without backend: `FileNotFoundError: SDK/scripts/xypm_disk_host.cpp`;
- staged SDK: `host_tool()` compiled outside the SDK; SDK tree hash unchanged;
  `xos_app build` passed after the host-tool build;
- staged SDK with b2 profile/package: `install` 22 files/14 mutations,
  `list`, `info`, `verify-installed`, `upgrade` revision 1, `remove` all passed;
- `release_smoke.check_sdk_devkit` passed on the staged SDK with a synthetic
  packaged binding.

## Checks not run

- Full `release_smoke.py` (requires rebuilding the release images and SDK with
  the new packaging).
- Full release packaging/asset replacement.
- P1 profile alignment: `xos-x86_64-sdk-local` still differs from the release
  work-disk DB `xos-x86_64-static-single-b2-v1`; installs into that disk need a
  b2-bound profile.
- Boot/run of a package installed by this environment; the image transaction and
  query/verification layers were tested.

## Next

P1 was delivered in [0210](0210_xypm_profile_alignment.md). The remaining release step is
to rebuild the SDK asset and run the full release smoke.
