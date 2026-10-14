#include <stdint.h>

uint64_t reference_swap(uint64_t x) {
  return ((x & UINT64_C(0xff)) << 56) | ((x & UINT64_C(0xff00)) << 40) |
         ((x & UINT64_C(0xff0000)) << 24) | ((x & UINT64_C(0xff000000)) << 8) |
         ((x >> 8) & UINT64_C(0xff000000)) | ((x >> 24) & UINT64_C(0xff0000)) |
         ((x >> 40) & UINT64_C(0xff00)) | (x >> 56);
}
uint64_t reference_rotate(uint64_t x, unsigned n) {
  n &= 63;
  return n ? (x << n) | (x >> (64 - n)) : x;
}
void reference_copy(uint8_t *dst, const uint8_t *src, unsigned n) {
  for (unsigned i = 0; i < n; ++i) dst[i] = src[i];
}
uint64_t reference_search(const uint8_t *src, unsigned n, uint8_t needle) {
  for (unsigned i = 0; i < n; ++i)
    if (src[i] == needle) return i;
  return UINT64_MAX;
}
static uint64_t load64(const uint8_t *p) {
  uint64_t x = 0;
  for (unsigned i = 0; i < 8; ++i) x |= (uint64_t)p[i] << (8*i);
  return x;
}
static void store64(uint8_t *p, uint64_t x) {
  for (unsigned i = 0; i < 8; ++i) p[i] = (uint8_t)(x >> (8*i));
}
uint64_t reference_add(unsigned p, uint8_t *z, unsigned m, const uint8_t *x,
                       unsigned n, const uint8_t *y) {
  uint64_t carry = 0;
  for (unsigned i = 0; i < p; ++i) {
    unsigned __int128 sum = carry;
    if (i < m) sum += load64(x + 8*i);
    if (i < n) sum += load64(y + 8*i);
    store64(z + 8*i, (uint64_t)sum);
    carry = (uint64_t)(sum >> 64);
  }
  return carry;
}
