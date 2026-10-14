#include "abi.h"
#include <assert.h>
#include <stdlib.h>
unsigned nondet_unsigned(void);
uint32_t nondet_u32(void);
_Bool nondet_bool(void);
#ifndef CASE
#define CASE 1
#endif
#ifndef STACK_SIZE
#define STACK_SIZE 128
#endif
/* CASE: bump/relay=1, aliases=2, pointer return=3, byte copy=4,
   undersized allocation=5, freed allocation=6, null=7, edge pointer=8,
   C global through argument=9. */
uint32_t c_global;
void harness(void) {
  uint8_t stack[STACK_SIZE];
  struct asmc_state s;
  frame_t frame = enter_objects(&s, stack, sizeof stack);
#if CASE == 4
  uint8_t *src = malloc(8), *dst = malloc(8), before[8], source_before[8];
  __CPROVER_assume(src && dst);
  unsigned n = nondet_unsigned();
  __CPROVER_assume(n <= 8);
  for (unsigned i = 0; i < 8; ++i) {
    before[i] = dst[i];
    source_before[i] = src[i];
  }
  arg_ptr(&s, 0, dst);
  arg_ptr(&s, 1, src);
  arg_value(&s, 2, n);
  asmc_target(&s);
  for (unsigned i = 0; i < 8; ++i) {
    assert(dst[i] == (i < n ? source_before[i] : before[i]));
    assert(src[i] == source_before[i]);
  }
  free(src); free(dst);
#else
#if CASE == 5
  uint32_t *a = malloc(3);
#else
  uint32_t *a = malloc(8);
#endif
  __CPROVER_assume(a != 0);
  uint32_t initial = nondet_u32();
#if CASE != 5
  *a = initial;
#endif
#if CASE == 9
  c_global = initial;
  free(a);
  a = &c_global;
#endif
#if CASE == 6
  free(a);
#elif CASE == 7
  arg_ptr(&s, 0, 0);
#endif
#if CASE == 8
  arg_ptr(&s, 0, (uint8_t *)a + 7);
#elif CASE != 7
  arg_ptr(&s, 0, a);
#endif
#if CASE == 2
  uint32_t *other = malloc(4);
  __CPROVER_assume(other != 0);
  *other = nondet_u32();
  uint32_t before = *other;
  _Bool alias = nondet_bool();
  arg_ptr(&s, 1, alias ? a : other);
#endif
  asmc_target(&s);
#if CASE == 1 || CASE == 9
  assert(*a == initial + 1);
  assert((uint32_t)result_value(&s) == *a);
#elif CASE == 2
  assert(*a == initial + (alias ? 3 : 1));
  assert(*other == before + (alias ? 0 : 2));
  assert((uint32_t)result_value(&s) == *a);
  free(other);
#elif CASE == 3
  assert(result_ptr(&s) == a + 1);
  assert(*a == initial);
#endif
#if CASE != 6 && CASE != 9
  free(a);
#endif
#endif
  check_frame(&s, &frame);
}
