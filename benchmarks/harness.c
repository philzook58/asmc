#include "asmc_x86.h"

/* Independent synthetic workloads. Uninitialized inputs/bytes are arbitrary in
 * CBMC; all runs retain native bounds, return, ABI and unwinding obligations. */
void harness(void) {
  uint8_t ram[BENCH_RAM];
  struct asmc_state s;
#ifdef ASMC_OBJECT_MEMORY
  struct asmc_sysv_frame frame = asmc_sysv_setup_objects_model(&s, ram, sizeof(ram));
#else
  struct asmc_sysv_frame frame = asmc_sysv_setup_ram_model(&s, ram, 0x1000, sizeof(ram));
#endif
  uint64_t x, y;
  asmc_sysv_arg64(&s, 0, x);
  asmc_sysv_arg64(&s, 1, y);

#if BENCH_KIND == 2 || BENCH_KIND == 3
#ifdef ASMC_OBJECT_MEMORY
  uint8_t buffer[BENCH_SIZE];
  uint8_t *data = buffer;
  asmc_sysv_arg_ptr(&s, 0, data);
#else
  uint8_t *data = ram;
  asmc_sysv_arg64(&s, 0, 0x1000);
#endif
  uint64_t index;
#ifdef BENCH_FIXED_INDEX
  index = 0;
#else
  __CPROVER_assume(index <= BENCH_SIZE - 8);
#endif
  asmc_sysv_arg64(&s, 1, index);
#if BENCH_KIND == 2
  uint64_t expected = 0;
  for (unsigned i = 0; i < 8; ++i)
    expected |= (uint64_t)data[index + i] << (8 * i);
#else
  asmc_sysv_arg64(&s, 2, x);
  uint64_t probe;
  __CPROVER_assume(probe < BENCH_SIZE && (probe < index || probe >= index + 8));
  uint8_t before = data[probe];
  uint64_t expected = x;
#endif
#elif BENCH_KIND == 4
  uint64_t expected = x;
  for (unsigned i = 0; i < BENCH_SIZE; ++i) expected += (y >> i) & 1;
#elif BENCH_KIND == 5
  uint64_t mask = UINT64_MAX >> (64 - BENCH_SIZE);
  __CPROVER_assume(x <= mask && y <= mask);
  uint64_t expected = (x * x + 2 * x * y + y * y) & mask;
#elif BENCH_KIND == 6
  /* Separate C objects, not subarrays of one allocation. */
  #include "objects.h"
#ifdef BENCH_BAD_POINTER
  selected = 0;
  uint64_t expected = 0;
#else
  uint64_t expected = *selected;
#endif
  asmc_sysv_arg_ptr(&s, 0, selected);
#elif BENCH_KIND == 7
  uint64_t expected = x;
#else
  uint64_t expected = x + BENCH_SIZE;
#endif
#ifdef BENCH_BAD
  ++expected;
#endif

  ASMC_TARGET(&s);
  asmc_sysv_check(&s, &frame);
  uint64_t actual = asmc_sysv_result64(&s);
#if BENCH_KIND == 5
  actual &= mask;
#endif
  __CPROVER_assert(actual == expected, "synthetic functional specification");
#if BENCH_KIND == 3
  __CPROVER_assert(data[probe] == before, "byte outside write remains unchanged");
#endif
}
