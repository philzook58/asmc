#include "wrappers.h"
#include <assert.h>

uint32_t nondet_u32(void);
unsigned nondet_uint(void);

/* Ordinary C callers need no machine registers, stack addresses, or RAM mapping. */
void harness(void) {
  uint32_t data[4];
  for (unsigned i = 0; i < 4; ++i) data[i] = nondet_u32();
  unsigned n = nondet_uint();
  __CPROVER_assume(n <= 4);
  uint32_t expected = 0;
  for (unsigned i = 0; i < n; ++i) expected += data[i];
  uint32_t result = sum_words(data, n);
  assert(result == expected);
  assert(add_one(result) == expected + 1); /* Both additions wrap modulo 2^32. */
}
