/* Independently written tests for complete-access bounds and immutability. */
.text
.globl read32
.type read32,@function
read32:
  mov (%rdi),%eax
  ret
.size read32,.-read32
.globl read64
.type read64,@function
read64:
  mov (%rdi),%rax
  ret
.size read64,.-read64
.globl write32
.type write32,@function
write32:
  movl $0,(%rdi)
  ret
.size write32,.-write32
.section .rodata
.globl constant_bytes
constant_bytes:
  .byte 0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88
.section .note.GNU-stack,"",@progbits
