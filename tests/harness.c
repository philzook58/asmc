#include "asmc_x86.h"
#include <assert.h>

uint64_t nondet_u64(void);
unsigned nondet_unsigned(void);
uint8_t nondet_u8(void);
uint64_t reference_swap(uint64_t);
uint64_t reference_rotate(uint64_t, unsigned);
void reference_copy(uint8_t *, const uint8_t *, unsigned);
uint64_t reference_search(const uint8_t *, unsigned, uint8_t);
uint64_t reference_add(unsigned, uint8_t *, unsigned, const uint8_t *, unsigned, const uint8_t *);

/* CASE values: inc=1, byte=2, word=3, dword=4, signed max=5,
   unsigned max=6, swap=7, rotate=8, add2=9, sub2=10, copy=11,
   search=12, read64=13, memory edge=14, address wrap=15,
   corrupt return=16, compiled C kernel=17, loop bound=18. */
#ifndef CASE
#define CASE 1
#endif
void harness(void) {
  struct memory { uint8_t bytes[256]; } memory, reference;
  struct asmc_state s;
  s.ram = memory.bytes; s.ram_base = 0x1000; s.ram_size = sizeof(memory.bytes);
  asmc_assume_flags(&s);
  ASMC_REG_BYTE(&s, ASMC_DF) = 0; /* SysV requires a clear direction flag. */
  asmc_setup_stack(&s, 0x10c8);
  uint64_t x = nondet_u64(), y = nondet_u64();
  unsigned n = nondet_unsigned();
  asmc_set_reg(&s, ASMC_RDI, 8, x);
  asmc_set_reg(&s, ASMC_RSI, 8, y);
  uint64_t saved[] = {
    asmc_get_reg(&s, ASMC_RBX, 8), asmc_get_reg(&s, ASMC_RBP, 8),
    asmc_get_reg(&s, ASMC_R12, 8), asmc_get_reg(&s, ASMC_R13, 8),
    asmc_get_reg(&s, ASMC_R14, 8), asmc_get_reg(&s, ASMC_R15, 8)
  };
  uint64_t expected = 0;
  unsigned m = 0, p = 0;
#if CASE == 1
  expected = x + 1;
#elif CASE == 2
  expected = (x & ~UINT64_C(0xffff)) | 0x1234;
#elif CASE == 3
  expected = (x & ~UINT64_C(0xffff)) | 0x4321;
#elif CASE == 4
  expected = (uint32_t)x;
#elif CASE == 5
  expected = (int64_t)x < (int64_t)y ? y : x;
#elif CASE == 6
  expected = x < y ? y : x;
#elif CASE == 7
  expected = reference_swap(x);
#elif CASE == 8
  asmc_set_reg(&s, ASMC_RSI, 8, n);
  expected = reference_rotate(x, n);
#elif CASE == 9 || CASE == 10
  asmc_set_reg(&s, ASMC_RDI, 8, 0x1040);
  asmc_set_reg(&s, ASMC_RSI, 8, 0x1000);
  asmc_set_reg(&s, ASMC_RDX, 8, 0x1020);
#elif CASE == 11 || CASE == 18
  __CPROVER_assume(n <= 32);
#ifdef ZERO_LENGTH
  __CPROVER_assume(n == 0);
#endif
#if CASE == 18
  __CPROVER_assume(n == 32);
#endif
  asmc_set_reg(&s, ASMC_RDI, 8, 0x1040);
  asmc_set_reg(&s, ASMC_RSI, 8, 0x1000);
  asmc_set_reg(&s, ASMC_RDX, 8, n);
  expected = 0x1040;
#ifdef ZERO_LENGTH
  /* A zero-length destination at the region edge is valid. The bad loop
     faults within nine iterations, giving a concrete memory counterexample
     instead of merely exceeding its unwinding bound. */
  asmc_set_reg(&s, ASMC_RDI, 8, 0x10f8);
  expected = 0x10f8;
#endif
#elif CASE == 12
  __CPROVER_assume(n <= 32);
  asmc_set_reg(&s, ASMC_RDI, 8, 0x1000);
  asmc_set_reg(&s, ASMC_RSI, 8, n);
  asmc_set_reg(&s, ASMC_RDX, 8, nondet_u8());
  expected = reference_search(memory.bytes, n, (uint8_t)asmc_get_reg(&s, ASMC_RDX, 8));
#elif CASE == 13
  /* An unaligned, full-width access ending at the buffer boundary. */
  s.ram_size = 255;
  asmc_set_reg(&s, ASMC_RDI, 8, 0x10f7);
  expected = asmc_load(&s, 0x10f7, 8);
#elif CASE == 14
  asmc_set_reg(&s, ASMC_RDI, 8, 0x10f9);
#elif CASE == 15
  asmc_set_reg(&s, ASMC_RDI, 8, UINT64_MAX - 3);
#elif CASE == 17
  expected = (x ^ y) + 17;
#elif CASE == 19
#ifdef INPUT_P
  p = INPUT_P; m = INPUT_M; n = INPUT_N;
#else
  m = nondet_unsigned(); p = nondet_unsigned();
#endif
  __CPROVER_assume(m <= 2 && n <= 2 && p <= 2);
  asmc_set_reg(&s, ASMC_RDI, 8, p);
  asmc_set_reg(&s, ASMC_RSI, 8, 0x1040);
  asmc_set_reg(&s, ASMC_RDX, 8, m);
  asmc_set_reg(&s, ASMC_RCX, 8, 0x1000);
  asmc_set_reg(&s, ASMC_R8, 8, n);
  asmc_set_reg(&s, ASMC_R9, 8, 0x1020);
#elif CASE == 20
  expected = (uint64_t)(int64_t)(int8_t)x;
#elif CASE == 21
  expected = (uint8_t)x;
#elif CASE == 22
  expected = x * y;
#elif CASE == 23
  s.ram_base = UINT64_MAX - 10;
  asmc_set_reg(&s, ASMC_RDI, 8, UINT64_MAX - 8);
#endif
  reference = memory;
#if CASE == 9 || CASE == 10
  struct asmc_state ref = s; ref.ram = reference.bytes;
  unsigned __int128 a = (unsigned __int128)asmc_load(&ref, 0x1008, 8) << 64;
  a |= asmc_load(&ref, 0x1000, 8);
  unsigned __int128 b = (unsigned __int128)asmc_load(&ref, 0x1028, 8) << 64;
  b |= asmc_load(&ref, 0x1020, 8);
#if CASE == 9
  unsigned __int128 result = a + b;
  expected = result < a;
#else
  unsigned __int128 result = a - b;
  expected = a < b;
#endif
  asmc_store(&ref, 0x1040, 8, (uint64_t)result);
  asmc_store(&ref, 0x1048, 8, (uint64_t)(result >> 64));
#elif CASE == 11 || CASE == 18
  reference_copy(reference.bytes + 64, reference.bytes, n);
#elif CASE == 19
  expected = reference_add(p, reference.bytes + 64, m, reference.bytes, n, reference.bytes + 32);
#endif

  asmc_target(&s);
  assert(asmc_get_reg(&s, ASMC_RAX, 8) == expected);
#if CASE == 22
  assert(asmc_get_reg(&s, ASMC_RDX, 8) == (uint64_t)(((unsigned __int128)x * y) >> 64));
#endif
  assert(asmc_get_reg(&s, ASMC_RSP, 8) == 0x10d0);
  assert(asmc_get_reg(&s, ASMC_RBX, 8) == saved[0]);
  assert(asmc_get_reg(&s, ASMC_RBP, 8) == saved[1]);
  assert(asmc_get_reg(&s, ASMC_R12, 8) == saved[2]);
  assert(asmc_get_reg(&s, ASMC_R13, 8) == saved[3]);
  assert(asmc_get_reg(&s, ASMC_R14, 8) == saved[4]);
  assert(asmc_get_reg(&s, ASMC_R15, 8) == saved[5]);
  /* All application bytes are observable; the upper half is stack scratch. */
  for (unsigned i = 0; i < 32; ++i) {
    assert(memory.bytes[i] == reference.bytes[i]);
    assert(memory.bytes[32+i] == reference.bytes[32+i]);
    assert(memory.bytes[64+i] == reference.bytes[64+i]);
    assert(memory.bytes[96+i] == reference.bytes[96+i]);
  }
}
