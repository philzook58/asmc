.text
.macro function name
.globl \name
.type \name,@function
\name:
.endm
.macro endfunction name
.size \name,.-\name
.endm

function inc
mov %rdi,%rax
add $1,%rax
ret
endfunction inc
function inc_bad
mov %rdi,%rax
add $2,%rax
ret
endfunction inc_bad
function alias_byte
mov %rdi,%rax
mov $0x34,%al
mov $0x12,%ah
ret
endfunction alias_byte
function alias_word
mov %rdi,%rax
mov $0x4321,%ax
ret
endfunction alias_word
function alias_dword
mov %edi,%eax
ret
endfunction alias_dword
function sext
movsbq %dil,%rax
ret
endfunction sext
function zext
movzbl %dil,%eax
ret
endfunction zext
function mulfull
mov %rdi,%rax
mul %rsi
ret
endfunction mulfull

function max_signed
mov %rdi,%rax
cmp %rsi,%rdi
jge 1f
mov %rsi,%rax
1: ret
endfunction max_signed
function max_signed_cmov
mov %rdi,%rax
cmp %rsi,%rdi
cmovl %rsi,%rax
ret
endfunction max_signed_cmov
function max_unsigned
mov %rdi,%rax
cmp %rsi,%rdi
jae 1f
mov %rsi,%rax
1: ret
endfunction max_unsigned
function max_unsigned_cmov
mov %rdi,%rax
cmp %rsi,%rdi
cmovb %rsi,%rax
ret
endfunction max_unsigned_cmov
function max_bad
mov %rdi,%rax
cmp %rsi,%rdi
jbe 1f
mov %rsi,%rax
1: ret
endfunction max_bad

function swap
mov %rdi,%rax
bswap %rax
ret
endfunction swap
function rotate
mov %rdi,%rax
mov %esi,%ecx
rol %cl,%rax
ret
endfunction rotate

function add2
mov (%rsi),%rax
add (%rdx),%rax
mov %rax,(%rdi)
mov 8(%rsi),%rax
adc 8(%rdx),%rax
mov %rax,8(%rdi)
mov $0,%eax
setc %al
ret
endfunction add2
function add2_bad
mov (%rsi),%rax
add (%rdx),%rax
mov %rax,(%rdi)
mov 8(%rsi),%rax
add 8(%rdx),%rax
mov %rax,8(%rdi)
mov $0,%eax
setc %al
ret
endfunction add2_bad
function sub2
mov (%rsi),%rax
sub (%rdx),%rax
mov %rax,(%rdi)
mov 8(%rsi),%rax
sbb 8(%rdx),%rax
mov %rax,8(%rdi)
mov $0,%eax
setc %al
ret
endfunction sub2

function copy
mov %rdi,%rax
test %rdx,%rdx
jz 2f
1: mov (%rsi),%cl
mov %cl,(%rdi)
inc %rsi
inc %rdi
dec %rdx
jnz 1b
2: ret
endfunction copy
function copy_rep
mov %rdi,%rax
mov %rdx,%rcx
rep movsb
ret
endfunction copy_rep
function copy_bad
mov %rdi,%rax
1: mov (%rsi),%cl
mov %cl,(%rdi)
inc %rsi
inc %rdi
dec %rdx
jnz 1b
ret
endfunction copy_bad
function copy_oob
mov %rdi,%rax
1: mov (%rsi),%cl
mov %cl,(%rdi)
inc %rsi
inc %rdi
dec %rdx
jns 1b
ret
endfunction copy_oob

function search
xor %eax,%eax
1: cmp %rsi,%rax
jae 3f
cmp %dl,(%rdi,%rax)
je 2f
inc %rax
jmp 1b
3: mov $-1,%rax
2: ret
endfunction search

function read64
mov (%rdi),%rax
ret
endfunction read64
function corrupt_return
movq $0,(%rsp)
ret
endfunction corrupt_return
function clobber_saved
mov %rdi,%rax
add $1,%rax
xor %ebx,%ebx
ret
endfunction clobber_saved

function dead_unsupported
jmp 1f
ud2
1: mov %rdi,%rax
add $1,%rax
ret
endfunction dead_unsupported
function unsupported_div
xor %edx,%edx
div %rdi
ret
endfunction unsupported_div
function unsupported_simd
pxor %xmm0,%xmm0
ret
endfunction unsupported_simd
function unsupported_call
call inc
ret
endfunction unsupported_call
function unsupported_indirect
jmp *%rdi
endfunction unsupported_indirect
function unsupported_tls
mov %fs:0,%rax
ret
endfunction unsupported_tls
function outside_function
jmp inc
endfunction outside_function

.globl missing_size
missing_size:
mov %rdi,%rax
ret
.globl missing_size_end
missing_size_end:

.globl truncated
.type truncated,@function
truncated:
mov %rdi,%rax
ret
.size truncated,1
.section .note.GNU-stack,"",@progbits
