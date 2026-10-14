/* Independently written x86-64 implementation of rpn.c.
 * Four data-stack words occupy 16 bytes of the SysV red zone.
 */
.text
.globl rpn_asm
.type rpn_asm,@function
rpn_asm:
  xor %r8d,%r8d
  xor %r9d,%r9d
1:
  cmp %esi,%r9d
  jae 4f
  movzbl (%rdi,%r9),%ecx
  cmp $128,%ecx
  je 2f
  mov %ecx,-16(%rsp,%r8,4)
  inc %r8d
  jmp 3f
2:
  dec %r8d
  mov -16(%rsp,%r8,4),%eax
  dec %r8d
  add %eax,-16(%rsp,%r8,4)
  inc %r8d
3:
  inc %r9d
  jmp 1b
4:
  mov -16(%rsp),%eax
  ret
.size rpn_asm,.-rpn_asm
.section .note.GNU-stack,"",@progbits
