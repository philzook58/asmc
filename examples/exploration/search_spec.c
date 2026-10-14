#include "abi.h"
#include <assert.h>
int nondet_int(void);
unsigned nondet_uint(void);
unsigned linear_lower_bound(const int *, unsigned, int);

void harness(void) {
  uint8_t ram[128];
  struct asmc_state s;
  struct frame_type frame = enter(&s, ram, sizeof(ram));
  int data[4];
  unsigned n = nondet_uint();
  int key = nondet_int();
  __CPROVER_assume(n <= 4);
  for (unsigned i = 0; i < 4; ++i) {
    data[i] = nondet_int();
    if (i != 0 && i < n) __CPROVER_assume(data[i-1] <= data[i]);
    asmc_store(&s, 0x1000 + 4*i, 4, (uint32_t)data[i]);
  }
  arg(&s, 0, 0x1000); arg32(&s, 1, n); arg32(&s, 2, (uint32_t)key);
  asmc_target(&s);
  unsigned position = (unsigned)result(&s);
  assert(position == linear_lower_bound(data, n, key));
  /* ACSL contract translated into bounded, executable C obligations. */
  assert(position <= n);
  for (unsigned i = 0; i < 4; ++i) {
    assert(asmc_load(&s, 0x1000 + 4*i, 4) == (uint32_t)data[i]);
    if (i < n) assert(i < position ? data[i] < key : data[i] >= key);
  }
  abi_check(&s, &frame);
}
