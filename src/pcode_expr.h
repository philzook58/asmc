#pragma once
#include "lifter.h"
#include <util/expr.h>

/* Each operation builds a symbolic expression; it never executes the ALU. */
exprt pcode_expression(const PcodeOp &op, const std::vector<exprt> &inputs);
