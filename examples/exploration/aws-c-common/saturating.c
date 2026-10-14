/* Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0
 * Extracted from include/aws/common/math.fallback.inl; external linkage and
 * function name adapted for a standalone ASMC fixture. See LICENSE and NOTICE. */
#include <stdint.h>

uint32_t saturating_add(uint32_t a, uint32_t b) {
    if ((b > 0) && (a > (UINT32_MAX - b)))
        return UINT32_MAX;
    return a + b;
}
