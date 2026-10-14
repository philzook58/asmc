#include <stdint.h>

__attribute__((noinline)) uint32_t leaf(uint32_t x) { return x + 1; }
__attribute__((noinline)) uint32_t middle(uint32_t x) { return leaf(x) + 2; }
uint32_t nested(uint32_t x) { return middle(x) + leaf(x); }
uint32_t repeated(uint32_t x) { return leaf(x) + leaf(x + 3); }
uint32_t recursive(uint32_t n) {
  return n == 0 ? 0 : recursive(n - 1) + n;
}
uint32_t tail(uint32_t x) { return leaf(x); }

uint32_t mutual_odd(uint32_t n);
uint32_t mutual_even(uint32_t n) { return n == 0 ? 1 : mutual_odd(n - 1); }
uint32_t mutual_odd(uint32_t n) { return n == 0 ? 0 : mutual_even(n - 1); }
