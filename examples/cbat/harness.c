#include "abi.h"

void original(struct asmc_state *s);
void patched(struct asmc_state *s);

/* CASE: 1 signs, 2 switch edit, 3 pointer, 4 bit scan, 5 increment, 6 goto fail.
 * Uninitialized local inputs and register bytes are nondeterministic in CBMC. */
void harness(void) {
  uint8_t original_ram[256], patched_ram[256];
  struct asmc_state left;
  struct asmc_state right = left;
#ifdef ASMC_OBJECT_MEMORY
  /* Distinct stack objects have distinct encodings; set up each separately. */
  frame_t left_frame = enter_objects(&left, original_ram, sizeof(original_ram));
  frame_t right_frame = enter_objects(&right, patched_ram, sizeof(patched_ram));
#else
  frame_t left_frame = enter_ram(&left, original_ram, sizeof(original_ram));
  right = left;
  for (unsigned i = 0; i < sizeof(original_ram); ++i)
    patched_ram[i] = original_ram[i];
  right.ram = patched_ram;
  frame_t right_frame = left_frame;
#endif

#if CASE == 1
  int32_t x, y;
  arg32(&left, 0, x); arg32(&right, 0, x);
  arg32(&left, 1, y); arg32(&right, 1, y);
  uint8_t expected = (x < 0) == (y < 0);
#elif CASE == 2
  uint32_t status;
  arg32(&left, 0, status); arg32(&right, 0, status);
#elif CASE == 3
  int32_t input;
  int32_t original_data = input, patched_data = input;
  arg_ptr(&left, 0, &original_data); arg_ptr(&right, 0, &patched_data);
#elif CASE == 4
  uint8_t input;
  arg32(&left, 0, input); arg32(&right, 0, input);
  uint32_t expected = 0;
  if (input != 0)
    while (((input >> expected) & 1) == 0) ++expected;
#elif CASE == 5
  uint64_t input;
  asmc_sysv_arg64(&left, 0, input); asmc_sysv_arg64(&right, 0, input);
#elif CASE == 6
  uint8_t original_events = 0, patched_events = 0, signature;
  arg_ptr(&left, 0, &original_events); arg_ptr(&right, 0, &patched_events);
  arg_ptr(&left, 1, &signature); arg_ptr(&right, 1, &signature);
#else
#error "Choose CASE=1..6"
#endif

  original(&left);
  patched(&right);
  check_frame(&left, &left_frame);
  check_frame(&right, &right_frame);

#if CASE == 1
  uint8_t before = result_bool(&left), after = result_bool(&right);
  assert(before == expected);
  assert(after == expected);
#elif CASE == 2
  uint8_t before = result_bool(&left), after = result_bool(&right);
  assert(before == (status == 1)); /* DEPLOY */
#ifdef ASMC_FIXED_SWITCH
  assert(after == (status == 1));
#else
  assert(after == (status == 0 || status == 1)); /* NAV fall-through */
#endif
#elif CASE == 3
  int32_t before = (int32_t)result(&left), after = (int32_t)result(&right);
  assert(before == (input > 12 ? -1 : 0));
  __CPROVER_assert(original_data == input && patched_data == input, "pointed-to inputs unchanged");
#elif CASE == 4
  uint32_t before = (uint32_t)result(&left), after = (uint32_t)result(&right);
  assert(before == expected);
  assert(after == expected);
#elif CASE == 5
  uint64_t before = result(&left), after = result(&right);
  assert(before == input + 1);
  assert(after == input + 1);
  /* The patched version changes caller-saved RDI; that is allowed. */
#elif CASE == 6
  uint8_t before = (uint8_t)result(&left), after = (uint8_t)result(&right);
  assert(before == 0 && after == 0);
#ifdef ASMC_RECORD_CALLS
  assert(original_events == 3 && patched_events == 15);
  __CPROVER_assert(original_events == patched_events, "selected call effects agree");
#else
  assert(original_events == 0 && patched_events == 0);
#endif
#endif
  __CPROVER_assert(before == after, "original and patched declared results agree");
}
