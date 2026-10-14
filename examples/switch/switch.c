/* Independently written switch whose cases discourage a value lookup table. */
#include <stdint.h>
uint64_t choose(unsigned tag, uint64_t x) {
  switch (tag) {
  case 0: return x + 3;
  case 1: return x ^ 17;
  case 2: return x * 5;
  case 3: return x >> 7;
  case 4: return x - 11;
  case 5: return x | 32;
  case 6: return x & 127;
  case 7: return (x << 9) ^ x;
  default: return x;
  }
}
