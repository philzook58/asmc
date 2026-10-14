#include <stddef.h>
#include <stdint.h>

/* Small independent specifications, inspired by the projects in README.md. */
uint64_t count_bits(uint64_t x) {
  uint64_t count = 0;
  for (unsigned i = 0; i < 64; ++i) count += (x >> i) & 1;
  return count;
}
uint64_t choose(uint64_t x, uint64_t y, uint64_t condition) {
  return condition ? y : x;
}
uint32_t sum_words(const uint32_t *data, size_t n) {
  uint32_t sum = 0;
  for (size_t i = 0; i < n; ++i) sum += data[i];
  return sum; /* Deliberately modular, including overflow. */
}
void swap_words(uint32_t *a, uint32_t *b) {
  uint32_t old_a = *a, old_b = *b;
  *a = old_b;
  *b = old_a;
}
