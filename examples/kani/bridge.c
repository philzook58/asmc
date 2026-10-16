#include "asmc_x86.h"

/* Keep Rust independent of the machine-state struct's representation.
   Each test links one lifted ASMC_TARGET into this ordinary C ABI bridge. */
#ifdef SWAP
uint32_t machine_swap(uint32_t *a, uint32_t *b) {
  uint8_t stack[64];
  struct asmc_state st;
  asmc_sysv_arg_ptr(&st, 0, a);
  asmc_sysv_arg_ptr(&st, 1, b);
  asmc_sysv_call_objects_model(&st, stack, sizeof stack);
  return 0;
}
#else
uint64_t machine_add_one(uint64_t x) {
  uint8_t stack[64];
  struct asmc_state st;
  asmc_sysv_arg64(&st, 0, x);
  asmc_sysv_call_objects_model(&st, stack, sizeof stack);
  return asmc_sysv_result64(&st);
}
#endif
