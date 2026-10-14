.text
.macro function name
.globl \name
.type \name,@function
\name:
.endm
.macro endfunction name
.size \name,.-\name
.endm
function zero_test
  li zero, 99
  add a0,a0,zero
  addi a0,a0,1
  ret
endfunction zero_test
function argument32
  mv a0,a0
  ret
endfunction argument32
function load32
  lw a0,0(a0)
  ret
endfunction load32
function bad_return
  addi ra,ra,2
  ret
endfunction bad_return
function bad_saved
  li s0,0
  ret
endfunction bad_saved
function bad_gp
  li gp,0
  ret
endfunction bad_gp
function bad_tp
  li tp,0
  ret
endfunction bad_tp
function bad_s11
  li s11,0
  ret
endfunction bad_s11
function all_args
  add a0,a0,a1
  add a0,a0,a2
  add a0,a0,a3
  add a0,a0,a4
  add a0,a0,a5
  add a0,a0,a6
  add a0,a0,a7
  ret
endfunction all_args
function bad_sp
  addi sp,sp,16
  ret
endfunction bad_sp
function divide
  div a0,a0,a1
  ret
endfunction divide
function indirect
  jr a0
endfunction indirect
function caller
  call argument32
  ret
endfunction caller
#if __riscv_xlen == 64
function add_word
  addiw a0,a0,1
  ret
endfunction add_word
#endif
