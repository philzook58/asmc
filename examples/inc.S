.text
.globl inc
.type inc,@function
inc:
  mov %rdi,%rax
  add $1,%rax
  ret
.size inc,.-inc
.section .note.GNU-stack,"",@progbits
