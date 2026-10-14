#include "pcode_expr.h"
#include <util/arith_tools.h>
#include <util/bitvector_expr.h>
#include <util/bitvector_types.h>
#include <util/std_expr.h>
#include <stdexcept>

namespace {
unsigned width(const exprt &x) { return to_bitvector_type(x.type()).get_width(); }
exprt boolean(const exprt &x) { return notequal_exprt(x, from_integer(0, x.type())); }
exprt sign(const exprt &x) { return extractbit_exprt(x, from_integer(width(x)-1, unsignedbv_typet(32))); }
exprt signed_value(const exprt &x) { return typecast_exprt(x, signedbv_typet(width(x))); }
exprt shift(const exprt &x, const exprt &amount, ghidra::OpCode opcode) {
  exprt shifted = opcode == ghidra::CPUI_INT_LEFT ? exprt(shl_exprt(x, amount)) :
                  opcode == ghidra::CPUI_INT_RIGHT ? exprt(lshr_exprt(x, amount)) :
                  exprt(ashr_exprt(signed_value(x), amount));
  exprt overflow = from_integer(0, x.type());
  if (opcode == ghidra::CPUI_INT_SRIGHT)
    overflow = if_exprt(sign(x), from_integer(-1, x.type()), overflow);
  // Widen the amount before comparing: a narrow shift count cannot represent
  // the operand width (e.g. an 8-bit amount and a 256-bit operand).
  auto count_type = unsignedbv_typet(std::max(width(amount), 32u));
  return if_exprt(binary_relation_exprt(typecast_exprt(amount, count_type), ID_ge,
                                       from_integer(width(x), count_type)),
                  overflow, typecast_exprt(shifted, x.type()));
}
}

exprt pcode_expression(const PcodeOp &op, const std::vector<exprt> &args) {
  using namespace ghidra;
  if (!op.output) throw std::runtime_error("ALU operation has no output");
  const auto result_type = unsignedbv_typet(op.output->size * 8);
  const auto &a = args.at(0);
  auto b = [&]() -> const exprt & { return args.at(1); };
  exprt result;
  switch (op.opcode) {
  case CPUI_COPY: case CPUI_INT_ZEXT: result = a; break;
  case CPUI_INT_SEXT: result = signed_value(a); break;
  case CPUI_INT_ADD: result = plus_exprt(a, b()); break;
  case CPUI_INT_SUB: result = minus_exprt(a, b()); break;
  case CPUI_INT_MULT: result = mult_exprt(a, b()); break;
  case CPUI_INT_AND: result = bitand_exprt(a, b()); break;
  case CPUI_INT_OR: result = bitor_exprt(a, b()); break;
  case CPUI_INT_XOR: result = bitxor_exprt(a, b()); break;
  case CPUI_INT_NEGATE: result = bitnot_exprt(a); break;
  case CPUI_INT_2COMP: result = unary_minus_exprt(a); break;
  case CPUI_INT_EQUAL: result = equal_exprt(a, b()); break;
  case CPUI_INT_NOTEQUAL: result = notequal_exprt(a, b()); break;
  case CPUI_INT_LESS: result = less_than_exprt(a, b()); break;
  case CPUI_INT_LESSEQUAL: result = binary_relation_exprt(a, ID_le, b()); break;
  case CPUI_INT_SLESS: result = less_than_exprt(signed_value(a), signed_value(b())); break;
  case CPUI_INT_SLESSEQUAL: result = binary_relation_exprt(signed_value(a), ID_le, signed_value(b())); break;
  case CPUI_INT_CARRY: result = less_than_exprt(plus_exprt(a, b()), a); break;
  case CPUI_INT_SCARRY:
    // Signed add overflows iff equal-sign operands produce a different sign.
    result = and_exprt(equal_exprt(sign(a), sign(b())), notequal_exprt(sign(plus_exprt(a, b())), sign(a)));
    break;
  case CPUI_INT_SBORROW:
    // Signed subtraction overflows iff different-sign operands change a's sign.
    result = and_exprt(notequal_exprt(sign(a), sign(b())), notequal_exprt(sign(minus_exprt(a, b())), sign(a)));
    break;
  case CPUI_INT_LEFT: case CPUI_INT_RIGHT: case CPUI_INT_SRIGHT:
    result = shift(a, b(), op.opcode); break;
  case CPUI_BOOL_NEGATE: result = not_exprt(boolean(a)); break;
  case CPUI_BOOL_AND: result = and_exprt(boolean(a), boolean(b())); break;
  case CPUI_BOOL_OR: result = or_exprt(boolean(a), boolean(b())); break;
  case CPUI_BOOL_XOR: result = notequal_exprt(boolean(a), boolean(b())); break;
  case CPUI_PIECE: result = concatenation_exprt(a, b(), result_type); break;
  case CPUI_SUBPIECE: {
    // The offset is in bytes, and may exceed the input width.
    auto count_type = unsignedbv_typet(std::max(width(b()), 32u) + 3);
    exprt bits = mult_exprt(typecast_exprt(b(), count_type), from_integer(8, count_type));
    result = shift(a, bits, CPUI_INT_RIGHT); break;
  }
  case CPUI_POPCOUNT: result = popcount_exprt(a, result_type); break;
  case CPUI_LZCOUNT: result = count_leading_zeros_exprt(a, true, result_type); break;
  default: throw std::runtime_error(std::string("unsupported p-code operation: ") + get_opname(op.opcode));
  }
  return typecast_exprt(result, result_type);
}
