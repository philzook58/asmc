/* Copyright 2018-2025 The simdjson authors. MIT; see LICENSE.
 * Adapted from fallback/numberparsing_defs.h. The argument is the already
 * packed little-endian word, replacing memcpy and C++ scaffolding.
 * Upstream credits Johnny Lee: https://johnnylee-sde.github.io/Fast-numeric-string-to-int/
 */
#include <stdint.h>

uint32_t parse_eight(uint64_t val) {
  val = (val & UINT64_C(0x0F0F0F0F0F0F0F0F)) * 2561 >> 8;
  val = (val & UINT64_C(0x00FF00FF00FF00FF)) * 6553601 >> 16;
  return (uint32_t)((val & UINT64_C(0x0000FFFF0000FFFF)) * UINT64_C(42949672960001) >> 32);
}
