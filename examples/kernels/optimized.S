.text
.globl count_bits_fast
.type count_bits_fast,@function
count_bits_fast:
  popcnt %rdi,%rax
  ret
.size count_bits_fast,.-count_bits_fast

.globl choose_fast
.type choose_fast,@function
choose_fast:
  mov %rdi,%rax
  test %rdx,%rdx
  cmovne %rsi,%rax
  ret
.size choose_fast,.-choose_fast
.section .note.GNU-stack,"",@progbits
