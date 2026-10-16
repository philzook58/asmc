/* From Philip Zucker's play/tutorial.ipynb. */
.text
.globl answer, increment, minimum, stack_scratch, corrupt_return, swap_spills
.type answer,@function
answer:
  mov $42,%rax
  ret
.size answer,.-answer
.type increment,@function
increment:
  lea 1(%rdi),%rax
  ret
.size increment,.-increment
/* The notebook's mymax uses cmovb this way: it computes unsigned minimum. */
.type minimum,@function
minimum:
  mov %rdi,%rax
  cmp %rdi,%rsi
  cmovb %rsi,%rax
  ret
.size minimum,.-minimum
.type stack_scratch,@function
stack_scratch:
  movq $42,-8(%rsp)
  ret
.size stack_scratch,.-stack_scratch
.type corrupt_return,@function
corrupt_return:
  movq $42,(%rsp)
  ret
.size corrupt_return,.-corrupt_return
/* Explicit spills reproduce the tutorial's -O0 swap layout independently of
   compiler version. Arguments may alias these saved pointers in RAM mode. */
.type swap_spills,@function
swap_spills:
  push %rbp
  mov %rsp,%rbp
  mov %rdi,-24(%rbp)
  mov %rsi,-32(%rbp)
  mov -24(%rbp),%rax
  mov (%rax),%eax
  mov %eax,-4(%rbp)
  mov -32(%rbp),%rax
  mov (%rax),%edx
  mov -24(%rbp),%rax
  mov %edx,(%rax)
  mov -32(%rbp),%rax
  mov -4(%rbp),%edx
  mov %edx,(%rax)
  pop %rbp
  ret
.size swap_spills,.-swap_spills
.section .note.GNU-stack,"",@progbits
