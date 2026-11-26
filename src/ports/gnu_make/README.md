# GNU Make for XOS glibc

Build GNU Make 4.4.1 against a verified XOS glibc SDK with
`stdio_transfer`. Supply the pinned GNU release archive, detached signature
and GNU keyring. The builder verifies the release signer, keeps the upstream
source and COPYING alongside its build, and writes a receipt for the static
target ELF. The host needs GNU Make, gpgv and the SDK's recorded cross tools.

```sh
python3 scripts/build_gnu_make.py \
  --archive "$gnu_make_archive" --signature "$gnu_make_signature" \
  --keyring "$gnu_keyring" --sdk "$kit/sdk" --profile "$kit/profile.json" \
  --output-dir build/gnu_make
```

Use `build/gnu_make/target/make` as `/usr/bin/gmake` for the glibc
candidate. Recipes use `/usr/bin/dash`. GNU Make's local scheduler uses
`posix_spawn` and `waitpid`, with translated standard descriptors for
recipes and captured output. The build disables message catalogs, loadable
modules and Guile. Guest tests use the C locale.
Recursive jobserver and output synchronization require additional XOS support.

The frozen sbase Make recipe remains at `scripts/build_make.py`. Use the
independent guest gate with a system image, dash and stdio-enabled probe to
validate the selected GNU Make behavior.
