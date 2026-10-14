/* Copyright (c) 2020-2026 Fraunhofer FOKUS. MIT; see LICENSE.
 * ASMC adaptation: replace ACSL header inclusion with the original C typedefs. */

#include <stdint.h>
typedef int value_type;
typedef unsigned int size_type;

size_type lower_bound(const value_type* a, size_type n, value_type v)
{
  size_type left  = 0u;
  size_type right = n;

  /*@
    loop invariant bound:  0 <= left <= right <= n;
    loop invariant left:   StrictUpperBound(a, 0,  left, v);
    loop invariant right:  LowerBound(a, right, n, v);

    loop assigns left, right;
    loop variant right - left;
  */
  while (left < right) {
    const size_type middle = left + (right - left) / 2u;

    if (a[middle] < v) {
      left = middle + 1u;
    }
    else {
      right = middle;
    }
  }

  return left;
}
