/* Independently written RV32/RV64 execution probe and Linux process entry. */
#if __riscv_xlen == 64
#define STORE sd
#define LOAD ld
#define WORD 8
#else
#define STORE sw
#define LOAD lw
#define WORD 4
#endif
.text
.globl _start
.type _start,@function
_start:
  call main
  li a7,93
  ecall
.size _start,.-_start

.globl probe
.type probe,@function
probe:
  addi sp,sp,-16
  STORE ra,0(sp)
  add t0,a0,a1
  STORE t0,0*WORD(a2)
  slt t0,a0,a1
  STORE t0,1*WORD(a2)
  sltu t0,a0,a1
  STORE t0,2*WORD(a2)
  sll t0,a0,a1
  STORE t0,3*WORD(a2)
  sra t0,a0,a1
  STORE t0,4*WORD(a2)
  lb t0,0(a2)
  STORE t0,5*WORD(a2)
  jal ra,probe_helper
  LOAD ra,0(sp)
  addi sp,sp,16
  ret
.size probe,.-probe

.globl probe_helper
.type probe_helper,@function
probe_helper:
  xor a0,a0,a1
  ret
.size probe_helper,.-probe_helper
.section .note.GNU-stack,"",@progbits
