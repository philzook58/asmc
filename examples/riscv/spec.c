#include "asmc_riscv.h"
#if ASMC_RISCV_XLEN == 32
typedef uint32_t word;
typedef int32_t sword;
#else
typedef uint64_t word;
typedef int64_t sword;
#endif
word nondet_word(void);
uint32_t nondet_u32(void);
uint8_t nondet_u8(void);
word inc(word), shift(word, word), multiply(word, word);
sword maximum(sword, sword);
uint32_t sum(const uint32_t *, word);
void copy(uint8_t *, const uint8_t *, word);

void harness(void) {
  uint8_t ram[256];
  struct asmc_state s;
  struct asmc_riscv_frame frame = asmc_riscv_enter(&s, ram, 0x1000, sizeof(ram), 0x10f0);
  word x = nondet_word(), y = nondet_word();
  asmc_riscv_arg(&s, 0, x); asmc_riscv_arg(&s, 1, y);
#if CASE == 5
  uint32_t data[4];
  for (unsigned i = 0; i < 4; ++i) {
    data[i] = nondet_u32(); asmc_store(&s, 0x1000 + 4*i, 4, data[i]);
  }
  __CPROVER_assume(x <= 4);
  asmc_riscv_arg(&s, 0, 0x1000); asmc_riscv_arg(&s, 1, x);
#elif CASE == 6
  uint8_t data[32];
  for (unsigned i = 0; i < 32; ++i) data[i] = ram[i] = nondet_u8();
  __CPROVER_assume(x <= 4);
  asmc_riscv_arg(&s, 0, 0x1010); asmc_riscv_arg(&s, 1, 0x1000); asmc_riscv_arg(&s, 2, x);
#elif CASE == 7
  uint32_t value = nondet_u32();
  asmc_riscv_arg32(&s, 0, value);
#elif CASE == 8
  asmc_riscv_arg(&s, 0, 0x1000);
  asmc_store(&s, 0x1000, 4, (uint32_t)x);
#elif CASE == 9
  s.ram_base = UINT32_MAX - 1; s.ram_size = 4;
  asmc_riscv_arg(&s, 0, UINT32_MAX - 1);
#elif CASE == 10
  asmc_riscv_arg32(&s, 0, (uint32_t)x);
#elif CASE == 11
  word total = 0;
  for (unsigned i = 0; i < 8; ++i) {
    word value = nondet_word(); total += value;
    asmc_riscv_arg(&s, i, value);
  }
#elif CASE == 12
  s.ram_base = UINT32_MAX - 31; s.ram_size = 24;
  asmc_riscv_arg(&s, 0, UINT32_MAX - 1); /* Complete word access wraps XLEN. */
#endif
  asmc_target(&s);
#if CASE == 1
  assert((word)asmc_riscv_result(&s) == inc(x));
#elif CASE == 2
  assert((sword)asmc_riscv_result(&s) == maximum((sword)x, (sword)y));
#elif CASE == 3
  assert((word)asmc_riscv_result(&s) == shift(x, y));
#elif CASE == 4
  assert((word)asmc_riscv_result(&s) == multiply(x, y));
#elif CASE == 5
  assert((uint32_t)asmc_riscv_result(&s) == sum(data, x));
  for (unsigned i = 0; i < 4; ++i) assert(asmc_load(&s, 0x1000 + 4*i, 4) == data[i]);
#elif CASE == 6
  copy(data + 16, data, x);
  for (unsigned i = 0; i < 32; ++i) assert(ram[i] == data[i]);
#elif CASE == 7
  assert(asmc_riscv_result(&s) == (uint64_t)(word)(sword)(int32_t)value);
#elif CASE == 8
  assert(asmc_riscv_result(&s) == (uint64_t)(word)(sword)(int32_t)x);
#elif CASE == 10
  assert(asmc_riscv_result(&s) == (uint64_t)(sword)(int32_t)((uint32_t)x + 1));
#elif CASE == 11
  assert((word)asmc_riscv_result(&s) == total);
#endif
  asmc_riscv_check(&s, &frame);
}
