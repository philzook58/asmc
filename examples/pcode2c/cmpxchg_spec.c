#include "asmc_x86.h"
#include <assert.h>

uint32_t nondet_u32(void);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  uint32_t old = nondet_u32(), expected = nondet_u32(), replacement = nondet_u32();
  uint8_t before[32];
  /* Offset 1 deliberately makes the four-byte access unaligned. */
  asmc_store(&s, 0x1001, 4, old);
  for (unsigned i = 0; i < 32; ++i) before[i] = ram[i];
  asmc_sysv_arg64(&s, 0, 0x1001);
  asmc_sysv_arg32(&s, 1, expected);
  asmc_sysv_arg32(&s, 2, replacement);
  asmc_target(&s);
  assert(asmc_sysv_result32(&s) == old);
  assert(asmc_load(&s, 0x1001, 4) == (old == expected ? replacement : old));
  assert(asmc_get_reg(&s, ASMC_ZF, 1) == (old == expected));
  for (unsigned i = 0; i < 32; ++i)
    if (i < 1 || i >= 5) assert(ram[i] == before[i]);
  asmc_sysv_check(&s, &frame);
}
