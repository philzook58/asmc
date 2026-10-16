#include "asmc_x86.h"
int nondet_int(void);
unsigned nondet_uint(void);

void harness(void) {
  uint8_t stack[256];
  struct asmc_state st;
  int data[4], before[4];
  for (unsigned k = 0; k < 4; ++k)
    data[k] = before[k] = nondet_int();

#ifdef FIXED_INDICES
  /* Leave data[1] as a canary for the extra-write mutant. */
  unsigned i = 0, j = 2;
#else
  unsigned i = nondet_uint(), j = nondet_uint();
  __CPROVER_assume(i < 4 && j < 4);
#endif
  asmc_sysv_arg_ptr(&st, 0, &data[i]);
  asmc_sysv_arg_ptr(&st, 1, &data[j]);
  asmc_sysv_call_objects_model(&st, stack, sizeof stack);

  __CPROVER_assert(data[i] == before[j], "swap first value");
  __CPROVER_assert(data[j] == before[i], "swap second value");
  for (unsigned k = 0; k < 4; ++k)
    if (k != i && k != j)
      __CPROVER_assert(data[k] == before[k], "swap unchanged element");
}
