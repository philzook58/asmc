#include "wrappers.h"
#include <assert.h>
uint32_t nondet_u32(void);
void harness(void) {
  uint32_t value = nondet_u32();
  assert(add_one(value) == value + 1);
}
