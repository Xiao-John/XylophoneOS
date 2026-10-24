# SPDX-License-Identifier: Apache-2.0
.text
.global answer
.type answer,@function
answer:
    mov $42, %eax
    ret
.size answer, .-answer
.section .note.GNU-stack,"",@progbits
