.text
.globl machine_add_one
.type machine_add_one,@function
machine_add_one:
  lea 1(%rdi),%eax
  ret
.size machine_add_one,.-machine_add_one

.globl machine_sum
.type machine_sum,@function
machine_sum:
  xor %eax,%eax
  mov %esi,%ecx
  test %ecx,%ecx
  jz 2f
1:
  add (%rdi),%eax
  add $4,%rdi
  dec %ecx
  jnz 1b
2:
  ret
.size machine_sum,.-machine_sum
.section .note.GNU-stack,"",@progbits
