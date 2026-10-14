/* Independently written literal/add calculator, inspired by Hutton's Razor.
 * Tokens 0..127 push that literal; token 128 adds the top two stack entries.
 * The caller supplies a well-formed program with depth <= 4 and final depth 1.
 */
#include <stdint.h>
uint32_t rpn(const uint8_t *code, unsigned n) {
  uint32_t stack[4];
  unsigned depth = 0;
  for (unsigned i = 0; i < n; ++i) {
    if (code[i] == 128) {
      uint32_t b = stack[--depth];
      stack[depth - 1] += b;
    } else stack[depth++] = code[i];
  }
  return stack[0];
}
