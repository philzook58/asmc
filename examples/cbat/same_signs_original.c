/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */
#include <stdbool.h>

bool same_signs(int x, int y) {
    // When x is negative
    if(x < 0){
        // They have the same sign if x is negative too
        if (y < 0) { return true; }
        else { return false; }
    // When x is positive
    } else{
        // They have the same sign if y is positive too
        if (y >= 0) { return true; }
        else { return false; }
    }
}
