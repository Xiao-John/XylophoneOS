# 0210 — XYPm release profile alignment (b2) and local-profile denial

## Scope

P1 of the blind-test XYPm correction.  Align SDK profile creation with the
0.0.2-1103 release work disk (`xos-x86_64-static-single-b2-v1`) and keep local
profiles development-only.  Do not weaken the transaction's profile equality
check.

## Changes

- `scripts/sdk_adopt_profile.py`
  - added `--base-profile` (relative paths resolve from CWD, then the SDK);
  - added `--id`; with a base profile and no `--id`, the base id is retained;
  - default remains `xos-x86_64-sdk-local` from the v1 base for development.
- `scripts/xypm_image.py`
  - DB profile mismatch now names the image profile, selected profile and the
    matching `config/package/*.json`; states local profiles are development-only.
- `scripts/xypm_format.py`
  - package/profile mismatch now names both ids and the matching config file;
    local-profile installs against a b2 package are rejected before opening the
    transaction.
- `scripts/release_smoke.py`
  - `sdk_xypm_rejects_local_profile_on_release_image`: a b2 probe package is
    rejected under a local profile, the message names the b2 config, and no
    output image is produced.
- `docs/releases/SDK_DEVELOPING.md`, `docs/usage/userland/xpk_packages.md`
  - document the b2-bound adoption command and explicitly prohibit local-profile
    installation to the release disk.

## Evidence

Workspace: `build/xypm_p1/`.

```text
adopt_sdk.py --base-profile config/package/xos_x86_64_static_single_b2_v1.json \
  -o profile_b2.json
# id=xos-x86_64-static-single-b2-v1, base_profile=same, tree bound to current SDK
```

- b2 profile build: exit 0;
- b2 package pack: exit 0, target b2;
- install with stock b2 profile: exit 0, 36 verified files, 30 mutations;
- install b2 package with local profile: exit 1:
  `package target profile mismatch: package='xos-x86_64-static-single-b2-v1'
  selected='xos-x86_64-sdk-local'; use config/package/xos_x86_64_static_single_b2_v1.json`;
- install local-built package with local profile on the b2 image: exit 1,
  `database profile mismatch: image='xos-x86_64-static-single-b2-v1'
  selected='xos-x86_64-sdk-local'; use config/package/xos_x86_64_static_single_b2_v1.json`,
  no output image produced;
- release gate `sdk_xypm_rejects_local_profile_on_release_image`: passed;
- release gate `sdk_xypm_install_query_remove`: passed.

## Diagnostics tests

`tests/xypm_profile_errors.py` covers the b2/local package-profile mismatch message,
the config-path hint, a missing hint, and the separate feature mismatch.  It passes:

```text
Ran 3 tests ... OK
```

## Not run

- Full release rebuild / asset replacement.
- Full `release_smoke.py` end-to-end; the two new gate functions were run
  individually against a staged SDK and a release work-disk copy.

## Notes

The b2-bound profile uses the b2 feature set but the current SDK tree hash.  The
stock `config/package/xos_x86_64_static_single_b2_v1.json` remains the profile
used to open the release image database; the adopted b2 profile is for building
packages whose `target_profile` matches that database.  No profile check was
relaxed.
