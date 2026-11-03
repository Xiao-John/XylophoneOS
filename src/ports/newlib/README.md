# newlib UTF-8 candidate

The XOS candidate build uses newlib 4.6.0.20260123 from the SHA-256 pinned by
`scripts/build_utf8_newlib.py`. `0001-reject-utf8-surrogates.patch` changes its
UTF-8 decoding and UCS-4 encoding to reject surrogate code points. The patch is
applied only to a new extracted build tree; it does not alter the vendored
prebuilt libraries. The source retains its original notices and the candidate
SDK includes `COPYING.NEWLIB`. XOS additions are Apache-2.0; upstream patch
context remains subject to its original terms. The candidate is not yet guest
qualified or approved for distribution.
