#include "asmc_x86.h"
#include <assert.h>

int nondet_int(void);
bool equal(int n, int a[], int b[]);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model_at(&s, ram, 0x1000, sizeof(ram), 0x10c8);
  int data[16];
  /* data[i] corresponds to four little-endian bytes at 0x1000 + 4*i.
     Bytes 0..63 hold application data; the stack is in the upper half. */
  for (unsigned i = 0; i < 16; ++i) {
    data[i] = nondet_int();
    asmc_store(&s, 0x1000 + 4*i, 4, (uint32_t)data[i]);
  }
  int n = nondet_int(), offset = nondet_int();
  __CPROVER_assume(n >= -2 && n <= 8 && offset >= 0 && offset <= 8);
  asmc_sysv_arg32(&s, 0, (uint32_t)n);
  asmc_sysv_arg64(&s, 1, 0x1000);                  /* a = data */
  asmc_sysv_arg64(&s, 2, 0x1000 + 4*(uint64_t)offset); /* b = data + offset */
  asmc_target(&s);
  assert(asmc_sysv_result_bool(&s) == equal(n, data, data + offset));
  /* Also check that the assembly did not modify the input array. */
  for (unsigned i = 0; i < 16; ++i)
    assert((uint32_t)asmc_load(&s, 0x1000 + 4*i, 4) == (uint32_t)data[i]);
  asmc_sysv_check(&s, &frame);
}
