#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
uint64_t probe(uint64_t, uint64_t, uint64_t *);
int main(void) {
  uint64_t a, b;
  while (scanf("%" SCNu64 " %" SCNu64, &a, &b) == 2) {
    uint64_t out[6];
    uint64_t result = probe(a, b, out);
    printf("%" PRIu64, result);
    for (unsigned i = 0; i < 6; ++i) printf(" %" PRIu64, out[i]);
    putchar('\n');
  }
  return 0;
}
