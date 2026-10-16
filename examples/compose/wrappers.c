#include "wrappers.h"
#include "asmc_x86.h"

void lifted_add_one(struct asmc_state *s);
void lifted_sum(struct asmc_state *s);

uint32_t add_one(uint32_t value) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model(&s, ram, 0x1000, sizeof(ram));
  asmc_sysv_arg32(&s, 0, value);
  lifted_add_one(&s);
  asmc_sysv_check(&s, &frame);
  return asmc_sysv_result32(&s);
}

uint32_t sum_words(const uint32_t *data, unsigned n) {
  assert(n <= 4);
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model(&s, ram, 0x1000, sizeof(ram));
  /* Explicit mapping: data[i] is represented at machine address 0x1000 + 4*i.
     These are copies of values, not casts from C pointers to machine addresses. */
  for (unsigned i = 0; i < n; ++i) asmc_store(&s, 0x1000 + 4*i, 4, data[i]);
  uint64_t before[16];
  for (unsigned i = 0; i < 16; ++i) before[i] = asmc_load(&s, 0x1000 + 8*i, 8);
  asmc_sysv_arg64(&s, 0, 0x1000);
  asmc_sysv_arg32(&s, 1, n);
  lifted_sum(&s);
  /* Check all application bytes, including unused padding; upper RAM is stack. */
  for (unsigned i = 0; i < 16; ++i) assert(asmc_load(&s, 0x1000 + 8*i, 8) == before[i]);
  asmc_sysv_check(&s, &frame);
  return asmc_sysv_result32(&s);
}
