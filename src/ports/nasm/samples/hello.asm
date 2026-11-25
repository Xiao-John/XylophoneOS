; SPDX-License-Identifier: Apache-2.0
; Minimal XOS self-test source shipped with the NASM package.
BITS 16
mov ax, 0x1234
int 0x10
hlt
