#include "asmc_x86.h"
#include <assert.h>
uint64_t nondet_u64(void);

void harness(void) {
  /* CBMC makes uninitialized locals nondeterministic. Registers we do not
     initialize remain arbitrary, so accidental dependencies are detectable. */
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  uint64_t x = nondet_u64();
  asmc_sysv_arg64(&s, 0, x);
  asmc_target(&s);
  assert(asmc_sysv_result64(&s) == x + 1);
  asmc_sysv_check(&s, &frame);
}
