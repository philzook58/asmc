#include "asmc_x86.h"
int nondet_int(void);
_Bool nondet_bool(void);

/* -1 covers both alias cases; 0/1 select one to test harness sensitivity. */
#ifndef ALIAS_CASE
#define ALIAS_CASE -1
#endif

void harness(void) {
  uint8_t stack[256];
  struct asmc_state st;
  int a = nondet_int(), b = nondet_int();
  _Bool same_object = ALIAS_CASE < 0 ? nondet_bool() : ALIAS_CASE;
  int *p = &a, *q = same_object ? p : &b;
  int old_p = *p, old_q = *q;

#ifdef MANUAL_ABI
  struct asmc_sysv_frame saved_abi =
      asmc_sysv_setup_objects_model(&st, stack, sizeof stack);
#endif
  asmc_sysv_arg_ptr(&st, 0, p);
  asmc_sysv_arg_ptr(&st, 1, q);
#ifdef MANUAL_ABI
  ASMC_TARGET(&st);
  asmc_sysv_check(&st, &saved_abi);
#else
  asmc_sysv_call_objects_model(&st, stack, sizeof stack);
#endif
  __CPROVER_assert(*p == old_q, "swap first value");
  __CPROVER_assert(*q == old_p, "swap second value");
}
