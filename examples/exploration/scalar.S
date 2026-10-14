/* Independently written assembly equivalents for the C specifications.
 * SWAR adaptation: Copyright 2018-2025 The simdjson authors.
 * See simdjson/LICENSE (MIT) and simdjson/swar.c for the attributed source.
 */
.text
.globl saturating_add_asm
.type saturating_add_asm,@function
saturating_add_asm:
  mov %edi,%eax
  add %esi,%eax
  jnc 1f
  mov $-1,%eax
1: ret
.size saturating_add_asm,.-saturating_add_asm

.globl parse_eight_asm
.type parse_eight_asm,@function
parse_eight_asm:
  mov %rdi,%rax
  movabs $0x0f0f0f0f0f0f0f0f,%rcx
  and %rcx,%rax
  imul $2561,%rax,%rax
  shr $8,%rax
  movabs $0x00ff00ff00ff00ff,%rcx
  and %rcx,%rax
  imul $6553601,%rax,%rax
  shr $16,%rax
  movabs $0x0000ffff0000ffff,%rcx
  and %rcx,%rax
  movabs $42949672960001,%rcx
  imul %rcx,%rax
  shr $32,%rax
  ret
.size parse_eight_asm,.-parse_eight_asm
.section .note.GNU-stack,"",@progbits
