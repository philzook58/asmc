#ifndef ASMC_EXAMPLE_WRAPPERS_H
#define ASMC_EXAMPLE_WRAPPERS_H
#include <stdint.h>

uint32_t add_one(uint32_t value);
/* Requires n <= 4 and data[0..n) readable. The input is unchanged. */
uint32_t sum_words(const uint32_t *data, unsigned n);
#endif
