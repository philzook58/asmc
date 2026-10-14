#include "asmc_x86.h"
#include <assert.h>
#include <stddef.h>

uint32_t nondet_u32(void);
unsigned nondet_uint(void);
uint32_t sum_words(const uint32_t *, size_t);
void swap_words(uint32_t *, uint32_t *);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_enter(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  uint32_t data[4];
  for (unsigned i = 0; i < 4; ++i) {
    data[i] = nondet_u32();
    asmc_store(&s, 0x1000 + 4*i, 4, data[i]);
  }
  unsigned n = nondet_uint();
#ifdef SWAP
  __CPROVER_assume(n < 4); /* Identical or disjoint, aligned C objects. */
  asmc_sysv_arg64(&s, 0, 0x1000);
  asmc_sysv_arg64(&s, 1, 0x1000 + 4*n);
  asmc_target(&s);
  swap_words(data, data + n);
#else
  __CPROVER_assume(n <= 4);
  asmc_sysv_arg64(&s, 0, 0x1000);
  asmc_sysv_arg64(&s, 1, n);
  asmc_target(&s);
  assert(asmc_sysv_result32(&s) == sum_words(data, n));
#endif
  for (unsigned i = 0; i < 4; ++i)
    assert(asmc_load(&s, 0x1000 + 4*i, 4) == data[i]);
  asmc_sysv_check(&s, &frame);
}
