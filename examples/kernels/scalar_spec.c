#include "asmc_x86.h"
#include <assert.h>

uint64_t nondet_u64(void);
uint64_t count_bits(uint64_t);
uint64_t choose(uint64_t, uint64_t, uint64_t);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  uint64_t x = nondet_u64(), y = nondet_u64(), condition = nondet_u64();
  asmc_sysv_arg64(&s, 0, x);
  asmc_sysv_arg64(&s, 1, y);
  asmc_sysv_arg64(&s, 2, condition);
  asmc_target(&s);
#ifdef SELECT
  assert(asmc_sysv_result64(&s) == choose(x, y, condition));
#else
  assert(asmc_sysv_result64(&s) == count_bits(x));
#endif
  asmc_sysv_check(&s, &frame);
}
