/* Adapted from pcode2c/examples/cmp/cmpxchg.s into a leaf function.
   This is sequential behavior, without LOCK or a concurrency model. */
.text
.globl compare_exchange
.type compare_exchange,@function
compare_exchange:
  mov %esi,%eax
  cmpxchg %edx,(%rdi)
  ret
.size compare_exchange,.-compare_exchange
.section .note.GNU-stack,"",@progbits
