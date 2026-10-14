/* Independently written routines; compile to ELF, then link their C harness. */
#include <stdint.h>
__attribute__((noinline)) uint32_t bump(uint32_t *p) {
  return ++*p;
}
uint32_t relay(uint32_t *p) {
  return bump(p);
}
uint32_t combine(uint32_t *a, uint32_t *b) {
  *a += 1;
  *b += 2;
  return *a;
}
uint32_t *next_word(uint32_t *p) {
  return p + 1;
}
void copy_bytes(uint8_t *dst, const uint8_t *src, unsigned n) {
  for (unsigned i = 0; i < n; ++i) dst[i] = src[i];
}
