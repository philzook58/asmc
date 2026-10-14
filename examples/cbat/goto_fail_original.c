/* Adapted from CBAT, copyright 2018/2019 The Charles Stark Draper Laboratory, Inc.
 * MIT licensed; see LICENSE and SOURCES.md for the pinned source and changes. */
#include <stdint.h>
#include "record_calls.h"

typedef uint8_t status;
typedef uint8_t hash;

/* Stub: log an error message. */
void errorLog(char *msg) {}

/* Stub */
status ReadyHash(hash *data) {
    RECORD_CALL(data, 1);
    // Do some stuff to prepare the hash.
    return 0;
}

/* Stub */
status SSLHashSHA1_update(hash *data) {
    RECORD_CALL(data, 2);
    // Do some stuff to update the hash.
    return 0;
}

/* Stub */
status SSLHashSHA1_final(hash *data) {
    RECORD_CALL(data, 4);
    // Do some stuff to finalize the hash.
    return 0;
}

/* Stub */
status SSLFreeBuffer(hash *data) {
    // Do some stuff to clear the buffer.
    return 0;
}

/* Stub */
status sslRawVerify(hash *data, hash *signature) {
    RECORD_CALL(data, 8);
    // Do some stuff to verify the SSL signature.
    return 0;
}

/* Stub */
status cleanUp(hash *data, status code) {
    SSLFreeBuffer(data);
    return code;
}

/* Check that the key exchange is signed correctly. */
status SSLVerifySignedServerKeyExchange(hash *data, hash *signature) {

    status code;

    if ((code = ReadyHash(data)) != 0)
        return cleanUp(data, code);
    if ((code = SSLHashSHA1_update(data)) != 0)
        return cleanUp(data, code);
        return cleanUp(data, code);
    if ((code = SSLHashSHA1_final(data)) != 0)
        return cleanUp(data, code);

    code = sslRawVerify(data, signature);

    return cleanUp(data, code);

}
