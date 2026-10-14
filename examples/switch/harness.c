#include "asmc_x86.h"
#include <assert.h>
unsigned nondet_unsigned(void);
uint64_t nondet_u64(void);
uint64_t choose(unsigned, uint64_t);
void harness(void) {
  uint8_t ram[128];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter_at_end(&s, ram, 0x1000, sizeof ram);
  unsigned tag = nondet_unsigned();
  uint64_t x = nondet_u64();
  asmc_sysv_arg32(&s, 0, tag);
  asmc_sysv_arg64(&s, 1, x);
  asmc_target(&s);
  assert(asmc_sysv_result64(&s) == choose(tag, x));
  asmc_sysv_check(&s, &frame);
}
