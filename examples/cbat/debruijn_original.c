/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */
#include <stdint.h>

int rightmost_index_8(uint8_t bb){
        if(bb == 0){
                return 0;
        }
        // mapping from log_2 n binary string from debruijn sequence to its
        // offset in the debruijn sequence
        int index8[8] = {0, 1, 2, 4, 7, 3, 6, 5};
        // debruijn sequence
        uint8_t debruijn8 = 0x17;
        // get lsb, then leftshift to get a unique 3 bit (log_2 8) sequence in
        // the top 3 bits
        // then rightshift by n - log_2 n = 5 to isolate that unique 3 bit
        // sequence then index into index8 array to get the lsb
        return index8[((uint8_t)((bb & -bb) * debruijn8)) >> 5];
}
