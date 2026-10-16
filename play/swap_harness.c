#include "asmc_x86.h"

int nondet_int(void);
_Bool nondet_bool(void);

void harness(void) {
  uint8_t stack[256];
  struct asmc_state st;

  int a = nondet_int(), b = nondet_int();
  int *p = &a;
  int *q = nondet_bool() ? &a : &b; /* Check both aliasing and distinct objects. */
  int old_p = *p, old_q = *q;
  asmc_sysv_arg_ptr(&st, 0, p);
  asmc_sysv_arg_ptr(&st, 1, q);

  asmc_sysv_call_objects_model(&st, stack, sizeof stack);
  assert(*p == old_q);
  assert(*q == old_p);
}
