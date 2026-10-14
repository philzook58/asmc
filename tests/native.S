/* Independently written execution oracle: arithmetic flags, aliases, shifts,
   memory writes, and a native call. The C runner observes every output word. */
.text
.globl probe
.type probe,@function
probe:
  mov %rdx,%r8
  mov %rdi,%rax
  add %rsi,%rax
  mov %rax,0(%r8)
  pushfq
  pop %r9
  and $0x8d5,%r9
  mov %r9,8(%r8)
  mov $0x5a,%al
  mov $0x12,%ah
  mov %rax,16(%r8)
  mov %eax,%eax
  mov %rax,24(%r8)
  mov %rsi,%rcx
  shl %cl,%rax
  mov %rax,32(%r8)
  sub $8,%rsp
  call probe_helper
  add $8,%rsp
  mov %rax,40(%r8)
  ret
.size probe,.-probe
.globl probe_helper
.type probe_helper,@function
probe_helper:
  xor %rdi,%rax
  rol $13,%rax
  ret
.size probe_helper,.-probe_helper
.section .note.GNU-stack,"",@progbits
