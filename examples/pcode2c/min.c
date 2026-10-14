/* Adapted from philzook58/pcode2c/examples/min/mymin.c; see README.md. */
#include <stdint.h>

int64_t mymin(int64_t x, int64_t y) {
  return x < y ? x : y;
}
