/* Independently written, simple C specifications. */
#include <stdint.h>

uint32_t add_spec(uint32_t a, uint32_t b) {
  uint64_t sum = (uint64_t)a + b;
  return sum > UINT32_MAX ? UINT32_MAX : (uint32_t)sum;
}

uint32_t digits_spec(uint64_t packed) {
  uint32_t value = 0;
  for (unsigned i = 0; i < 8; ++i)
    value = 10 * value + (uint8_t)(packed >> (8 * i)) - '0';
  return value;
}

unsigned linear_lower_bound(const int *a, unsigned n, int v) {
  unsigned i = 0;
  while (i < n && a[i] < v) ++i;
  return i;
}
