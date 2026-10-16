#include "pcode_expr.h"
#include <util/arith_tools.h>
#include <util/bitvector_types.h>
#include <util/namespace.h>
#include <util/simplify_expr.h>
#include <util/symbol_table.h>
#include <util/std_expr.h>
#include <util/bitvector_expr.h>
#include <util/message.h>
#include <solvers/flattening/boolbv.h>
#include <solvers/sat/satcheck.h>
#include <iostream>
#include <stdexcept>

namespace {
symbol_tablet symbols;
namespacet ns(symbols);
unsigned checks = 0;
exprt translated(ghidra::OpCode opcode, unsigned bits, const std::vector<exprt> &args) {
  return pcode_expression({opcode, Varnode{Space::unique, 0, bits/8}, {}, ""}, args);
}
void prove(const std::string &name, const exprt &actual, const exprt &reference,
           bool equivalent = true) {
  null_message_handlert messages;
  satcheckt sat(messages);
  boolbvt solver(ns, sat, messages);
  solver << notequal_exprt(actual, reference);
  const auto expected = equivalent ? decision_proceduret::resultt::D_UNSATISFIABLE :
                                    decision_proceduret::resultt::D_SATISFIABLE;
  if (solver() != expected)
    throw std::runtime_error("symbolic semantics: " + name);
  ++checks;
}
void symbolic_checks() {
  using namespace ghidra;
  for (unsigned bits : {8u, 16u, 32u, 64u}) {
    const unsignedbv_typet type(bits), wide(2*bits), byte(8);
    const symbol_exprt a("a", type), b("b", type), count("count", byte);
    const auto zero = from_integer(0, type);
    const auto sign_bit = from_integer(power(2, bits-1), type);
    const auto negative = notequal_exprt(bitand_exprt(a, sign_bit), zero);
    const auto widened = typecast_exprt(a, wide);
    const auto high_mask = from_integer((power(2, bits)-1) * power(2, bits), wide);
    prove("zext " + std::to_string(bits), translated(CPUI_INT_ZEXT, 2*bits, {a}), widened);
    prove("sext " + std::to_string(bits), translated(CPUI_INT_SEXT, 2*bits, {a}),
          if_exprt(negative, bitor_exprt(widened, high_mask), widened));
    auto signed_less = typecast_exprt(less_than_exprt(bitxor_exprt(a, sign_bit),
                                                    bitxor_exprt(b, sign_bit)), byte);
    prove("signed comparison " + std::to_string(bits),
          translated(CPUI_INT_SLESS, 8, {a,b}), signed_less);
    prove("piece " + std::to_string(bits), translated(CPUI_PIECE, 2*bits, {a,b}),
          bitor_exprt(shl_exprt(widened, from_integer(bits, byte)), typecast_exprt(b, wide)));
    for (unsigned offset : {0u, bits/16, bits/8-1, bits/8}) {
      exprt reference = offset == bits/8 ? exprt(from_integer(0, byte)) :
        exprt(typecast_exprt(lshr_exprt(a, from_integer(8*offset, byte)), byte));
      prove("subpiece " + std::to_string(bits),
            translated(CPUI_SUBPIECE, 8, {a, from_integer(offset, byte)}), reference);
    }
    for (auto opcode : {CPUI_INT_LEFT, CPUI_INT_RIGHT, CPUI_INT_SRIGHT}) {
      // Enumerate constant shifts as an independent specification of the
      // symbolic count, including every oversized count (not an assume).
      exprt reference = opcode == CPUI_INT_SRIGHT ?
        exprt(if_exprt(negative, from_integer(-1, type), zero)) : exprt(zero);
      for (unsigned n = 0; n < bits; ++n) {
        const auto k = from_integer(n, byte);
        exprt value = opcode == CPUI_INT_LEFT ? exprt(shl_exprt(a, k)) :
          opcode == CPUI_INT_RIGHT ? exprt(lshr_exprt(a, k)) :
          exprt(typecast_exprt(ashr_exprt(typecast_exprt(a, signedbv_typet(bits)), k), type));
        reference = if_exprt(equal_exprt(count, k), value, reference);
      }
      prove(std::string(get_opname(opcode)) + " " + std::to_string(bits),
            translated(opcode, bits, {a, count}), reference);
    }
    // Negative control: signed and unsigned comparisons must differ somewhere.
    prove("signed comparison mutation", translated(CPUI_INT_SLESS, 8, {a,b}),
          translated(CPUI_INT_LESS, 8, {a,b}), false);
  }
}
void expect(ghidra::OpCode opcode, unsigned bits, uint64_t a, uint64_t b,
            uint64_t expected, unsigned result_bits = 0) {
  if (!result_bits) result_bits = bits;
  PcodeOp op{opcode, Varnode{Space::unique, 0, result_bits/8}, {}, ""};
  std::vector<exprt> inputs{from_integer(mp_integer(a), unsignedbv_typet(bits)),
                            from_integer(mp_integer(b), unsignedbv_typet(bits))};
  auto result = pcode_expression(op, inputs);
  result = simplify_expr(result, ns);
  if (result.id() != ID_constant ||
      numeric_cast_v<uint64_t>(to_constant_expr(result)) != expected)
    throw std::runtime_error(std::string(ghidra::get_opname(opcode)) +
      " differs from independent arithmetic reference at " +
      std::to_string(a) + ", " + std::to_string(b) + ": " + result.pretty());
  ++checks;
}
}

int main() {
  try {
    using namespace ghidra;
    symbolic_checks();
    // Widened host arithmetic makes these overflow expectations independent
    // of the translator's sign-bit rules. Exhaust every 8-bit operand pair.
    for (unsigned a = 0; a < 256; ++a)
      for (unsigned b = 0; b < 256; ++b) {
        int sa = a < 128 ? a : int(a)-256, sb = b < 128 ? b : int(b)-256;
        expect(CPUI_INT_CARRY, 8, a, b, a+b > 255, 8);
        expect(CPUI_INT_SCARRY, 8, a, b, sa+sb < -128 || sa+sb > 127, 8);
        expect(CPUI_INT_SBORROW, 8, a, b, sa-sb < -128 || sa-sb > 127, 8);
      }
    for (unsigned bits : {8u,16u,32u,64u}) {
      uint64_t mask = bits == 64 ? UINT64_MAX : (UINT64_C(1) << bits)-1;
      uint64_t high = UINT64_C(1) << (bits-1);
      for (uint64_t a : {UINT64_C(0),UINT64_C(1),high,mask})
        for (uint64_t b : {UINT64_C(0),UINT64_C(1),high,mask}) {
          expect(CPUI_INT_ADD, bits, a, b, (a+b)&mask);
          expect(CPUI_INT_SUB, bits, a, b, (a-b)&mask);
          expect(CPUI_INT_CARRY, bits, a, b, b > mask-a, 8);
        }
      for (uint64_t n : {UINT64_C(0),UINT64_C(1),uint64_t(bits-1),uint64_t(bits),uint64_t(bits+1),UINT64_C(255)}) {
        expect(CPUI_INT_LEFT, bits, mask, n, n >= bits ? 0 : (mask << n)&mask);
        expect(CPUI_INT_RIGHT, bits, mask, n, n >= bits ? 0 : mask >> n);
        uint64_t signed_shift = n >= bits ? mask : n == 0 ? high :
          ((high >> n) | (mask ^ (mask >> n)));
        expect(CPUI_INT_SRIGHT, bits, high, n, signed_shift);
      }
      expect(CPUI_POPCOUNT, bits, mask, 0, bits, 8);
      expect(CPUI_LZCOUNT, bits, 0, 0, bits, 8);
    }
    expect(CPUI_SUBPIECE, 64, UINT64_C(0x123456789abcdef0), 7, 0x12, 8);
    expect(CPUI_SUBPIECE, 64, UINT64_MAX, 8, 0, 8);
    expect(CPUI_SUBPIECE, 64, UINT64_MAX, UINT64_MAX, 0, 8);
    Instruction instruction{0x1000, 1, "synthetic", {}, {}};
    instruction.ops.resize(10);
    if (relative_target(instruction, 5, {Space::constant,0xfffffffe,4}) != 3 ||
        relative_target(instruction, 5, {Space::constant,3,4}) != 8)
      throw std::runtime_error("signed p-code-relative branch offsets are wrong");
    bool rejected = false;
    try { relative_target(instruction, 0, {Space::constant,UINT64_MAX,8}); }
    catch (const std::runtime_error &) { rejected = true; }
    if (!rejected) throw std::runtime_error("invalid internal branch accepted");
    std::cout << "PASS " << checks << " arithmetic/shift checks and signed internal branches\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << error.what() << '\n';
    return 1;
  }
}
