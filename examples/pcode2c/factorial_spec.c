#include "asmc_x86.h"
#include <assert.h>

int nondet_int(void);
int fact(int x);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  int x = nondet_int();
  /* Negative inputs do not terminate normally; 13! overflows signed int. */
  __CPROVER_assume(x >= 0 && x <= 12);
  asmc_sysv_arg32(&s, 0, (uint32_t)x);
  asmc_target(&s);
  assert((int32_t)asmc_sysv_result32(&s) == fact(x));
  asmc_sysv_check(&s, &frame);
}
