#include "abi.h"
#include <assert.h>
uint8_t nondet_u8(void);
unsigned nondet_uint(void);
uint32_t rpn(const uint8_t *, unsigned);

void harness(void) {
  uint8_t ram[128], code[5];
  struct asmc_state s;
  struct frame_type frame = enter(&s, ram, sizeof(ram));
  unsigned n = nondet_uint(), depth = 0;
  uint32_t sum = 0;
  __CPROVER_assume(n <= 5);
  for (unsigned i = 0; i < 5; ++i) {
    code[i] = nondet_u8();
    ram[i] = code[i];
    if (i < n) {
      __CPROVER_assume(code[i] <= 128);
      if (code[i] == 128) {
        __CPROVER_assume(depth >= 2);
        --depth;
      } else {
        __CPROVER_assume(depth < 4);
        ++depth; sum += code[i];
      }
    }
  }
  __CPROVER_assume(depth == 1);
  arg(&s, 0, 0x1000); arg32(&s, 1, n);
  asmc_target(&s);
  assert((uint32_t)result(&s) == rpn(code, n));
  assert((uint32_t)result(&s) == sum);
  for (unsigned i = 0; i < 5; ++i) assert(ram[i] == code[i]);
  abi_check(&s, &frame);
}
