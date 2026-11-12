# newlib UTF-8 candidate

The XOS candidate build uses newlib 4.6.0.20260123 from the SHA-256 pinned by
`scripts/build_utf8_newlib.py`. `0001-reject-utf8-surrogates.patch` changes its
UTF-8 decoding and UCS-4 encoding to reject surrogate code points. The patch is
applied only to a new extracted build tree; it does not alter the vendored
prebuilt libraries. The source retains its original notices and the candidate
SDK includes `COPYING.NEWLIB`. XOS additions are Apache-2.0; upstream patch
context remains subject to its original terms. The candidate is not yet guest
qualified or approved for distribution.

## C11 and type-generic header fixes

The fixed input remains newlib 4.6.0.20260123. The patches retain upstream
copyright and license notices; their changes are distributed under each
modified file's existing terms.

- `0002_native_atomic_initialization.patch` initializes GCC's native `_Atomic`
  values without using the legacy fallback structure member `__val`.
- `0003_generic_math_dispatch.patch` selects long-double overloads on the same
  architectures as `math.h`, and uses compile-time choice so float results do
  not acquire double type through the conditional operator.

The ordinary, threading and UTF-8 newlib builders apply these patches to source before configuration.
SDK exporters apply the same patches after copying headers from an existing
prefix, so an older frozen binary prefix gets corrected header generation
without editing its files. No binary archive is changed by this header step.
The SDK source/input manifests include the generator and patches.

`python3 tests/newlib_headers_test.py` regenerates a private header tree from
the vendored input and exercises real C11 atomics and type-generic math with
the selected host C compiler. Target compiler/link/guest results remain
separate from this host regression.
