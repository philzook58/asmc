#include <stdint.h>
#if ASMC_RISCV_XLEN == 32
typedef uint32_t word;
typedef int32_t sword;
#else
typedef uint64_t word;
typedef int64_t sword;
#endif
word inc(word x) { return x + 1; }
sword maximum(sword x, sword y) { return x < y ? y : x; }
word shift(word x, word n) { return x >> (n & (ASMC_RISCV_XLEN - 1)); }
word multiply(word x, word y) { return x * y; }
uint32_t sum(const uint32_t *data, word n) {
  uint32_t result = 0;
  for (word i = 0; i < n; ++i) result += data[i];
  return result;
}
void copy(uint8_t *dst, const uint8_t *src, word n) {
  for (word i = 0; i < n; ++i) dst[i] = src[i];
}
