/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */
.text
.globl increment
.type increment,@function
increment:
inc     %rdi
    movq    %rdi, %rax
    ret
.size increment,.-increment
.section .note.GNU-stack,"",@progbits
