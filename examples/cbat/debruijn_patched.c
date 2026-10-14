/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */
#include <stdint.h>

int rightmost_index_8(uint8_t bb){
        if(bb == 0){
                return 0;
        }
        if((bb >> 0) & 1){
                return 0;
        }
        if((bb >> 1) & 1){
                return 1;
        }
        if((bb >> 2) & 1){
                return 2;
        }
        if((bb >> 3) & 1){
                return 3;
        }
        if((bb >> 4) & 1){
                return 4; }
        if((bb >> 5) & 1){
                return 5;
        }
        if((bb >> 6) & 1){
                return 6;
        }
        if((bb >> 7) & 1){
                return 7;
        }
}
