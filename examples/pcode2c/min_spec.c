#include "asmc_x86.h"
#include <assert.h>

int64_t nondet_i64(void);
int64_t mymin(int64_t x, int64_t y);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  /* The complete signed 64-bit domain, including INT64_MIN and INT64_MAX. */
  int64_t x = nondet_i64(), y = nondet_i64();
  asmc_sysv_arg64(&s, 0, (uint64_t)x);
  asmc_sysv_arg64(&s, 1, (uint64_t)y);
  asmc_target(&s);
  assert((int64_t)asmc_sysv_result64(&s) == mymin(x, y));
  asmc_sysv_check(&s, &frame);
}
