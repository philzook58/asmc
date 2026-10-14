/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */

int deref(int *num_1) {
    int num_2 = 12;
    if(*num_1 > num_2){
        return -1;
    }
    return 0;
}
