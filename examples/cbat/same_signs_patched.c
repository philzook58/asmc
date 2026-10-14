/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */
#include <stdbool.h>

bool same_signs(int x, int y) {
    return !((x ^ y) < 0);
}
