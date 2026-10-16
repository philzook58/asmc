#include <stdint.h>

uint32_t add42(uint32_t x) { return x + 42; }

/* Tutorial swap, originally https://www.philipzucker.com/asm_verify3/ */
void swap(int *a, int *b) {
  int tmp = *a;
  *a = *b;
  *b = tmp;
}

/* Incorrect: loses the original *a. */
void swap_bad(int *a, int *b) {
  *a = *b;
  *b = *a;
}

/* Correct for distinct int objects, incorrect when a == b. */
void swap_xor(int *a, int *b) {
  *a ^= *b;
  *b ^= *a;
  *a ^= *b;
}

/* Correct swapped values, but an extra write violates the frame condition. */
void swap_extra(int *a, int *b) {
  int tmp = *a;
  *a = *b;
  *b = tmp;
  a[1] = 0;
}
