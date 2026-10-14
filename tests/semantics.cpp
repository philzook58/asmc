#include "pcode_expr.h"
#include <util/arith_tools.h>
#include <util/bitvector_types.h>
#include <util/namespace.h>
#include <util/simplify_expr.h>
#include <util/symbol_table.h>
#include <iostream>
#include <stdexcept>

namespace {
symbol_tablet symbols;
namespacet ns(symbols);
unsigned checks = 0;
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
