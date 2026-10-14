#include <assert.h>
#ifdef ASMC_RISCV_XLEN
#include "asmc_riscv.h"
#else
#include "asmc_x86.h"
#endif
uint32_t nondet_u32(void);

void harness(void) {
  uint8_t ram[160];
  struct asmc_state s;
  uint32_t x = nondet_u32();
#if CASE == 3 || CASE == 5
  __CPROVER_assume(x <= 3);
#endif
#ifdef ASMC_RISCV_XLEN
  struct asmc_riscv_frame frame = asmc_riscv_enter(&s, ram, 0x1000, sizeof(ram), 0x1090);
  asmc_riscv_arg32(&s, 0, x);
#else
  struct asmc_sysv_frame frame = asmc_sysv_enter_at_end(&s, ram, 0x1000, sizeof(ram));
  asmc_sysv_arg32(&s, 0, x);
#endif
  asmc_target(&s);
#ifdef ASMC_RISCV_XLEN
  uint32_t result = (uint32_t)asmc_riscv_result(&s);
  asmc_riscv_check(&s, &frame);
#else
  uint32_t result = asmc_sysv_result32(&s);
  asmc_sysv_check(&s, &frame);
#endif
#if CASE == 1
  assert(result == (x + 3) + (x + 1));
#elif CASE == 2
  assert(result == (x + 1) + (x + 4));
#elif CASE == 3
  assert(result == x * (x + 1) / 2);
#elif CASE == 4
  assert(result == x + 1);
#elif CASE == 5
  assert(result == ((x & 1) == 0));
#endif
}
