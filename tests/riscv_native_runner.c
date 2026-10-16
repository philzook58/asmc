/* Freestanding QEMU user-mode runner: only Linux read/write/exit are needed.
   One input record is two fixed-width hexadecimal words plus a newline.
   Each output record contains the return value and six written words. */
#include <stdint.h>
typedef uintptr_t word;
word probe(word, word, word *);

static long syscall3(long number, long first, long second, long third) {
  register long a0 __asm__("a0") = first;
  register long a1 __asm__("a1") = second;
  register long a2 __asm__("a2") = third;
  register long a7 __asm__("a7") = number;
  __asm__ volatile("ecall" : "+r"(a0) : "r"(a1), "r"(a2), "r"(a7) : "memory");
  return a0;
}
static long transfer(long number, long fd, char *buffer, unsigned size) {
  unsigned done = 0;
  while (done < size) {
    long n = syscall3(number, fd, (long)(buffer + done), size - done);
    if (n <= 0) return done == 0 ? n : -1;
    done += n;
  }
  return done;
}
int main(void) {
  const unsigned digits = 2 * sizeof(word);
  char input[4 * sizeof(word) + 1], output[7 * (2 * sizeof(word) + 1)];
  for (;;) {
    long n = transfer(63, 0, input, sizeof input);
    if (n == 0) return 0;
    if (n != sizeof input || input[sizeof input - 1] != '\n') return 1;
    word args[2] = {0, 0}, observed[7];
    for (unsigned i = 0; i < 2 * digits; ++i) {
      unsigned digit = input[i] >= '0' && input[i] <= '9' ? input[i] - '0' :
        input[i] >= 'a' && input[i] <= 'f' ? input[i] - 'a' + 10 : 16;
      if (digit >= 16) return 2;
      args[i / digits] = (args[i / digits] << 4) | digit;
    }
    observed[0] = probe(args[0], args[1], observed + 1);
    for (unsigned i = 0; i < 7; ++i) {
      for (unsigned j = 0; j < digits; ++j)
        output[i * (digits + 1) + j] =
          "0123456789abcdef"[(observed[i] >> (4 * (digits - j - 1))) & 15];
      output[i * (digits + 1) + digits] = i == 6 ? '\n' : ' ';
    }
    if (transfer(64, 1, output, sizeof output) != sizeof output) return 3;
  }
}
