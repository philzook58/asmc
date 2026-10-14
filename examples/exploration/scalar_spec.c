#include "abi.h"
#include <assert.h>
uint32_t nondet_u32(void);
uint8_t nondet_u8(void);
uint32_t add_spec(uint32_t, uint32_t);
uint32_t digits_spec(uint64_t);
uint32_t parse_eight(uint64_t);

void harness(void) {
  uint8_t ram[64];
  struct asmc_state s;
  struct frame_type frame = enter(&s, ram, sizeof(ram));
#ifdef DIGITS
  uint64_t packed = 0;
  for (unsigned i = 0; i < 8; ++i) {
    uint8_t c = nondet_u8();
    __CPROVER_assume(c >= '0' && c <= '9');
#ifdef DIGIT_CONTRACT
#ifndef DIGIT_FULL
    if (i < 4) __CPROVER_assume(c == '0');
#endif
#endif
    packed |= (uint64_t)c << (8 * i);
  }
  arg(&s, 0, packed);
  asmc_target(&s);
  assert((uint32_t)result(&s) == parse_eight(packed));
#ifdef DIGIT_CONTRACT
  assert((uint32_t)result(&s) == digits_spec(packed));
#endif
#else
  uint32_t a = nondet_u32(), b = nondet_u32();
  arg32(&s, 0, a); arg32(&s, 1, b);
  asmc_target(&s);
  assert((uint32_t)result(&s) == add_spec(a, b));
#endif
  abi_check(&s, &frame);
}
