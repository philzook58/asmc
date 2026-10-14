/* Adapted from pcode2c/examples/all_equal/all_equal.c; see README.md. */
#include <stdbool.h>

bool equal(int n, int a[], int b[]) {
  for (int i = 0; i < n; ++i)
    if (a[i] != b[i])
      return false;
  return true;
}
