#include "translate.h"
#include "pcode_expr.h"
#include <util/arith_tools.h>
#include <util/bitvector_expr.h>
#include <util/bitvector_types.h>
#include <util/pointer_expr.h>
#include <util/std_expr.h>
#include <util/simplify_expr.h>
#include <stdexcept>

namespace {
const unsignedbv_typet byte_type(8), address_type(64);
exprt number(uint64_t n, const typet &type = address_type) { return from_integer(mp_integer(n), type); }
using Label = std::pair<uint64_t, size_t>;

class Translator {
  goto_modelt &model;
  const Instructions &instructions;
  namespacet ns;
  goto_functiont &function;
  goto_programt declarations;
  exprt state;
  const struct_typet &state_type;
  std::map<Label, goto_programt::targett> labels;
  std::map<std::pair<uint64_t, uint64_t>, symbol_exprt> unique_bytes;
  std::vector<std::pair<goto_programt::targett, Label>> jumps;
  std::vector<goto_programt::targett> returns;
  std::set<uint64_t> call_returns;
  std::set<uint64_t> dispatch_entries;
  std::optional<symbol_exprt> program_counter;
  std::vector<goto_programt::targett> dispatch_jumps;
  std::string listing;
  const ElfImage &image;
  const std::string target_name;
  const bool dispatch_branches;
  const bool object_memory;
  unsigned counter = 0;
  source_locationt location;

  exprt field(const std::string &name) const {
    const auto &type = state_type.component_type(name);
    if (type.is_nil()) throw std::runtime_error("runtime state is missing field: " + name);
    return member_exprt(state, name, type);
  }
  symbol_exprt fresh(const typet &type) {
    auto base = "asmc_tmp_" + std::to_string(counter++);
    symbolt symbol(target_name + "::" + base, type, ID_C);
    symbol.base_name = base;
    symbol.is_lvalue = true;
    symbol.is_thread_local = true;
    symbol.location = location;
    auto value = symbol.symbol_expr();
    if (model.symbol_table.add(symbol)) throw std::runtime_error("generated symbol collision");
    declarations.add(goto_programt::make_decl(code_declt(value), location));
    return value;
  }
  symbol_exprt snapshot(const exprt &value) {
    auto tmp = fresh(value.type());
    function.body.add(goto_programt::make_assignment(tmp, value, location));
    return tmp;
  }
  void check(const exprt &condition, const std::string &description) {
    auto loc = location;
    loc.set_property_class("asmc");
    loc.set_comment(description + "; " + id2string(location.get_comment()));
    function.body.add(goto_programt::make_assertion(condition, loc));
    // The property remains visible, but invalid accesses must not contaminate
    // later memory reads or generate meaningless pointer counterexamples.
    function.body.add(goto_programt::make_assumption(condition, location));
  }
  exprt memory_offset(const exprt &address, unsigned size) {
    auto a = snapshot(typecast_exprt(address, address_type));
    auto base = typecast_exprt(field("ram_base"), address_type);
    auto capacity = typecast_exprt(field("ram_size"), address_type);
    auto maximum = image.address_bits == 32 ? UINT32_MAX : UINT64_MAX;
    check(binary_relation_exprt(base, ID_le, number(maximum)), "RAM base outside address space");
    check(binary_relation_exprt(capacity, ID_le, minus_exprt(number(maximum), base)), "RAM region wraps");
    check(binary_relation_exprt(a, ID_ge, base), "memory address below RAM base");
    check(binary_relation_exprt(a, ID_le, number(maximum - (size - 1))), "memory access wraps");
    check(binary_relation_exprt(capacity, ID_ge, number(size)), "memory access wider than RAM");
    auto offset = snapshot(minus_exprt(a, base));
    check(binary_relation_exprt(offset, ID_le, minus_exprt(capacity, number(size))), "memory access outside RAM");
    return offset;
  }
  exprt memory_byte(const exprt &offset, unsigned i) {
    auto pointer = plus_exprt(field("ram"), plus_exprt(offset, number(i)));
    return dereference_exprt(pointer);
  }
  exprt object_pointer(const exprt &address, unsigned size, bool writing) {
    // The integer already carries CBMC's encoding. Do not decode object bits
    // ourselves, infer its origin, or fall back to machine-address regions.
    auto pointer = snapshot(typecast_exprt(address, field("ram").type()));
    exprt valid = writing ? exprt(w_ok_exprt(pointer, number(size))) :
                            exprt(r_ok_exprt(pointer, number(size)));
    auto loc = location;
    loc.set_property_class("asmc");
    loc.set_comment(std::string(writing ? "invalid CBMC object write" : "invalid CBMC object read") +
                    " (complete access); " + id2string(location.get_comment()));
    // Keep this as an assertion, not an assumption: invalid-pointer memory
    // primitives must not be used to prune away the very failures we seek.
    function.body.add(goto_programt::make_assertion(valid, loc));
    return pointer;
  }
  exprt object_byte(const exprt &pointer, unsigned i) {
    return dereference_exprt(plus_exprt(pointer, number(i)));
  }
  void store(const exprt &address, unsigned size, const exprt &value, uint64_t pc) {
    if (object_memory) {
      auto pointer = object_pointer(address, size, true);
      auto saved = snapshot(value);
      for (unsigned i = 0; i < size; ++i)
        function.body.add(goto_programt::make_assignment(object_byte(pointer, i),
          typecast_exprt(lshr_exprt(saved, number(i * 8)), byte_type), location));
    } else {
      auto offset = memory_offset(address, size);
      write_bytes({Space::ram, 0, size}, pc, value, offset);
    }
  }
  // A complete read must fit in RAM or one immutable ELF region. Keep the
  // machine address numeric; conditional expressions guard each backing object.
  exprt load(const exprt &address, unsigned size) {
    if (object_memory) {
      auto pointer = object_pointer(address, size, false);
      exprt::operandst bytes;
      for (unsigned i = size; i-- > 0;) bytes.push_back(object_byte(pointer, i));
      return bytes.size() == 1 ? bytes.front() : exprt(concatenation_exprt(bytes, unsignedbv_typet(size * 8)));
    }
    if (image.readonly.empty()) {
      auto offset = memory_offset(address, size);
      exprt::operandst bytes;
      for (unsigned i = size; i-- > 0;) bytes.push_back(memory_byte(offset, i));
      return bytes.size() == 1 ? bytes.front() : exprt(concatenation_exprt(bytes, unsignedbv_typet(size * 8)));
    }
    auto a = snapshot(typecast_exprt(address, address_type));
    auto base = field("ram_base"), capacity = field("ram_size");
    auto offset = minus_exprt(a, base);
    exprt in_ram = and_exprt(binary_relation_exprt(a, ID_ge, base),
      and_exprt(binary_relation_exprt(capacity, ID_ge, number(size)),
                binary_relation_exprt(offset, ID_le, minus_exprt(capacity, number(size)))));
    exprt permitted = in_ram;
    exprt::operandst bytes;
    for (unsigned i = size; i-- > 0;)
      bytes.push_back(if_exprt(in_ram, memory_byte(offset, i), number(0, byte_type)));
    for (const auto &region : image.readonly) {
      if (size > region.bytes.size()) continue;
      auto index = minus_exprt(a, number(region.begin));
      exprt hit = and_exprt(binary_relation_exprt(a, ID_ge, number(region.begin)),
        binary_relation_exprt(index, ID_le, number(region.bytes.size() - size)));
      permitted = or_exprt(permitted, hit);
      array_exprt contents({}, array_typet(byte_type, number(region.bytes.size())));
      for (auto b : region.bytes) contents.operands().push_back(number(b, byte_type));
      for (unsigned i = 0; i < size; ++i)
        bytes[size - 1 - i] = if_exprt(hit,
          index_exprt(contents, plus_exprt(index, number(i))), bytes[size - 1 - i]);
    }
    check(permitted, "read outside RAM and admitted ELF .rodata");
    return bytes.size() == 1 ? bytes.front() : exprt(concatenation_exprt(bytes, unsignedbv_typet(size * 8)));
  }
  exprt byte(const Varnode &node, uint64_t pc, unsigned i) {
    if (node.space == Space::reg) {
      auto offset = node.offset;
      if (image.riscv) {
        if (offset < 0x2000 || offset + node.size > 0x2000 + 32 * image.address_bits / 8)
          throw std::runtime_error("unsupported RISC-V non-GPR register");
        offset -= 0x2000; // Compact GPR bank; raw p-code/listings retain SLEIGH offsets.
      }
      auto regs = field("registers");
      const auto &array = to_array_type(regs.type());
      auto size = numeric_cast_v<uint64_t>(to_constant_expr(array.size()));
      if (offset > size || node.size > size - offset)
        throw std::runtime_error("unsupported register bank (SIMD/system register)");
      // FS/GS segment bases are outside this prototype's flat addressing model.
      if (!image.riscv && offset >= 0x100 && offset < 0x200)
        throw std::runtime_error("segment/TLS registers are unsupported");
      return index_exprt(regs, number(offset + i));
    }
    if (node.space == Space::unique) {
      auto key = std::make_pair(pc, node.offset + i);
      auto found = unique_bytes.find(key);
      if (found == unique_bytes.end()) found = unique_bytes.emplace(key, fresh(byte_type)).first;
      return found->second;
    }
    throw std::runtime_error("unsupported varnode address space");
  }
  exprt read(const Varnode &node, uint64_t pc) {
    if (node.size == 0 || node.size > 16) throw std::runtime_error("unsupported varnode width (maximum 128 bits)");
    auto type = unsignedbv_typet(node.size * 8);
    if (node.space == Space::constant) return number(node.offset, type);
    if (node.space == Space::ram) return load(number(node.offset), node.size);
    exprt::operandst bytes;
    for (unsigned i = node.size; i-- > 0; )
      bytes.push_back(typecast_exprt(byte(node, pc, i), byte_type));
    return bytes.size() == 1 ? bytes.front() : exprt(concatenation_exprt(bytes, type));
  }
  void write_bytes(const Varnode &node, uint64_t pc, const exprt &value,
                   std::optional<exprt> offset = {}) {
    // Snapshot once, BEFORE any byte is overwritten (e.g. AL aliases RAX).
    auto saved = snapshot(value);
    for (unsigned i = 0; i < node.size; ++i) {
      auto lhs = offset ? memory_byte(*offset, i) : byte(node, pc, i);
      exprt rhs = typecast_exprt(lshr_exprt(saved, number(i * 8)), lhs.type());
      function.body.add(goto_programt::make_assignment(lhs, rhs, location));
    }
  }
  Label target(const Instruction &insn, size_t i, const Varnode &node) {
    return node.space == Space::constant ? Label(insn.address, relative_target(insn, i, node)) : Label(node.offset, 0);
  }
  void jump(Label dest, const exprt &guard = true_exprt()) {
    auto instruction = function.body.add(goto_programt::make_incomplete_goto(guard, location));
    jumps.emplace_back(instruction, dest);
  }
  void dispatch_jump(uint64_t address) {
    function.body.add(goto_programt::make_assignment(*program_counter, number(address), location));
    dispatch_jumps.push_back(function.body.add(goto_programt::make_incomplete_goto(location)));
  }
public:
  Translator(goto_modelt &model, const Instructions &instructions, const std::string &listing,
             const ElfImage &image, const std::string &target, bool dispatch_branches, bool object_memory)
      : model(model), instructions(instructions), ns(model.symbol_table),
        function(model.goto_functions.function_map.at(target)),
        state(dereference_exprt(model.symbol_table.lookup_ref(function.parameter_identifiers.at(0)).symbol_expr())),
        state_type(ns.follow_tag(to_struct_tag_type(state.type()))), listing(listing), image(image), target_name(target),
        dispatch_branches(dispatch_branches || !image.indirect_targets.empty()), object_memory(object_memory) {
    dispatch_entries.insert(image.indirect_targets.begin(), image.indirect_targets.end());
    for (const auto &[pc, instruction] : instructions)
      for (auto index : instruction.reachable)
        if (index < instruction.ops.size() && instruction.ops[index].opcode == ghidra::CPUI_CALL) {
          call_returns.insert(pc + instruction.length);
          dispatch_entries.insert(instruction.ops[index].inputs.at(0).offset);
          dispatch_entries.insert(pc + instruction.length);
        }
    if (this->dispatch_branches)
      for (const auto &[pc, instruction] : instructions)
        for (auto index : instruction.reachable)
          if (index < instruction.ops.size()) {
            const auto &op = instruction.ops[index];
            if ((op.opcode == ghidra::CPUI_BRANCH || op.opcode == ghidra::CPUI_CBRANCH) &&
                op.inputs.at(0).space == Space::ram) {
              dispatch_entries.insert(op.inputs[0].offset);
              if (op.opcode == ghidra::CPUI_CBRANCH) dispatch_entries.insert(pc + instruction.length);
            }
          }
    dispatch_entries.insert(image.entry);
    // CBMC still uses this legacy location field for unwinding property IDs.
    location.set(ID_function, target_name);
  }

  void run() {
    function.body.clear();
    if (!image.readonly.empty()) {
      auto base = field("ram_base"), size = field("ram_size");
      auto maximum = image.address_bits == 32 ? UINT32_MAX : UINT64_MAX;
      check(binary_relation_exprt(base, ID_le, number(maximum)), "RAM base outside address space");
      check(binary_relation_exprt(size, ID_le, minus_exprt(number(maximum), base)), "RAM region wraps");
      for (const auto &region : image.readonly)
        check(or_exprt(binary_relation_exprt(plus_exprt(base, size), ID_le, number(region.begin)),
                       binary_relation_exprt(base, ID_ge, number(region.begin + region.bytes.size()))),
              "RAM overlaps immutable ELF .rodata");
    }
    for (auto address : call_returns)
      check(notequal_exprt(field("return_address"), number(address)), "return sentinel aliases a call continuation");
    std::optional<goto_programt::targett> dispatch;
    if (!call_returns.empty() || dispatch_branches) {
      // Merge all paths at one loop latch. Separate backward return edges make
      // CBMC unwind many overlapping loops, even for nonrecursive calls.
      program_counter = fresh(address_type);
      function.body.add(goto_programt::make_assignment(*program_counter, number(image.entry), location));
      dispatch = function.body.add(goto_programt::make_skip(location));
      for (auto pc : dispatch_entries)
        jump({pc, 0}, equal_exprt(*program_counter, number(pc)));
      check(false_exprt(), "unexpected instruction address");
      returns.push_back(function.body.add(goto_programt::make_incomplete_goto(location)));
    } else jump({image.entry, 0});
    unsigned line = 1;
    // First emit blocks with unresolved destinations; resolve their jumps
    // after all labels exist. std::list iterators remain stable while appending.
    for (const auto &[pc, insn] : instructions) {
      for (auto i : insn.reachable) {
        location = source_locationt();
        location.set(ID_function, target_name);
        location.set_file(listing);
        location.set_line(line++);
        location.set_comment(describe(insn, i));
        labels.emplace(Label(pc, i), function.body.add(goto_programt::make_skip(location)));
        try {
          if (i == insn.ops.size()) {
            if (dispatch_branches && dispatch_entries.count(pc + insn.length)) dispatch_jump(pc + insn.length);
            else jump({pc + insn.length, 0});
          }
          else {
            const auto &op = insn.ops[i];
            using namespace ghidra;
            if (op.opcode == CPUI_BRANCH) {
              if (dispatch_branches && op.inputs.at(0).space == Space::ram) dispatch_jump(op.inputs[0].offset);
              else jump(target(insn, i, op.inputs.at(0)));
            }
            else if (op.opcode == CPUI_CALL) dispatch_jump(op.inputs.at(0).offset);
            else if (op.opcode == CPUI_CBRANCH) {
              auto condition = read(op.inputs.at(1), pc);
              if (dispatch_branches && op.inputs.at(0).space == Space::ram) {
                jump({pc,i+1}, equal_exprt(condition, number(0, condition.type())));
                dispatch_jump(op.inputs[0].offset);
              } else {
                jump(target(insn, i, op.inputs.at(0)), notequal_exprt(condition, number(0, condition.type())));
                jump({pc,i+1});
              }
            } else if (op.opcode == CPUI_BRANCHIND) {
              auto destination = snapshot(typecast_exprt(read(op.inputs.at(0), pc), address_type));
              exprt permitted = false_exprt();
              for (auto address : image.indirect_targets)
                permitted = or_exprt(permitted, equal_exprt(destination, number(address)));
              check(permitted, "indirect jump outside supplied targets; add --indirect-target");
              function.body.add(goto_programt::make_assignment(*program_counter, destination, location));
              dispatch_jumps.push_back(function.body.add(goto_programt::make_incomplete_goto(location)));
            } else if (op.opcode == CPUI_RETURN) {
              auto destination = snapshot(typecast_exprt(read(op.inputs.at(0), pc), address_type));
              exprt permitted = equal_exprt(destination, field("return_address"));
              for (auto address : call_returns)
                permitted = or_exprt(permitted, equal_exprt(destination, number(address)));
              check(permitted, "unexpected return address");
              auto exits = program_counter ? equal_exprt(destination, field("return_address")) : exprt(true_exprt());
              returns.push_back(function.body.add(goto_programt::make_incomplete_goto(exits, location)));
              if (program_counter) {
                function.body.add(goto_programt::make_assignment(*program_counter, destination, location));
                dispatch_jumps.push_back(function.body.add(goto_programt::make_incomplete_goto(location)));
              }
            } else if (op.opcode == CPUI_LOAD) {
              if (op.memory_space != "ram") throw std::runtime_error("unsupported LOAD space");
              write_bytes(*op.output, pc, load(read(op.inputs.at(1), pc), op.output->size));
              jump({pc,i+1});
            } else if (op.opcode == CPUI_STORE) {
              if (op.memory_space != "ram") throw std::runtime_error("unsupported STORE space");
              store(read(op.inputs.at(1), pc), op.inputs.at(2).size, read(op.inputs.at(2), pc), pc);
              jump({pc,i+1});
            } else {
              std::vector<exprt> args;
              for (const auto &input : op.inputs) args.push_back(read(input, pc));
              auto value = pcode_expression(op, args);
              if (op.output->space == Space::ram)
                store(number(op.output->offset), op.output->size, value, pc);
              else write_bytes(*op.output, pc, value);
              jump({pc,i+1});
            }
          }
        } catch (const std::exception &error) {
          throw std::runtime_error(describe(insn, i) + ": " + error.what());
        }
      }
    }
    if (dispatch) {
      auto latch = function.body.add(goto_programt::make_skip(location));
      for (auto instruction : dispatch_jumps) instruction->complete_goto(latch);
      auto backedge = function.body.add(goto_programt::make_incomplete_goto(location));
      backedge->complete_goto(*dispatch);
    }
    auto exit = function.body.add(goto_programt::make_end_function(location));
    for (const auto &[instruction, dest] : jumps) instruction->complete_goto(labels.at(dest));
    for (auto instruction : returns) instruction->complete_goto(exit);
    function.body.instructions.splice(function.body.instructions.begin(), declarations.instructions);
    model.goto_functions.update();
    model.validate(validation_modet::EXCEPTION);
  }
};
}

void translate(goto_modelt &model, const Instructions &instructions, const std::string &listing,
               const ElfImage &image, const std::string &target, bool dispatch_branches, bool object_memory) {
  if (object_memory && !image.readonly.empty())
    throw std::runtime_error("CBMC-object memory cannot import ELF .rodata");
  if (const auto *mode = model.symbol_table.lookup("asmc_memory_is_objects")) {
    auto selected = simplify_expr(mode->value, namespacet(model.symbol_table));
    if (!selected.is_constant() ||
        numeric_cast_v<unsigned>(to_constant_expr(selected)) != unsigned(object_memory))
      throw std::runtime_error("template runtime memory mode differs from --memory; "
        "compile runtime with -DASMC_OBJECT_MEMORY for objects, without it for ram");
  }
  auto found = model.goto_functions.function_map.find(target);
  if (found == model.goto_functions.function_map.end() || found->second.parameter_identifiers.size() != 1)
    throw std::runtime_error("template must define void " + target + "(struct asmc_state *)");
  // Validate the small runtime ABI before using CBMC's checked type casts,
  // which would otherwise abort on a malformed user-provided template.
  namespacet ns(model.symbol_table);
  const auto &function_type = model.symbol_table.lookup_ref(target).type;
  const auto &parameter = model.symbol_table.lookup_ref(found->second.parameter_identifiers[0]).type;
  if (function_type.id() != ID_code || to_code_type(function_type).return_type().id() != ID_empty ||
      parameter.id() != ID_pointer || to_pointer_type(parameter).base_type().id() != ID_struct_tag)
    throw std::runtime_error("template has an incompatible " + target + " signature");
  const auto &state = ns.follow_tag(to_struct_tag_type(to_pointer_type(parameter).base_type()));
  const auto &registers = state.component_type("registers");
  if (registers.id() != ID_array || to_array_type(registers).element_type().id() != ID_unsignedbv ||
      to_unsignedbv_type(to_array_type(registers).element_type()).get_width() != 8 ||
      !to_array_type(registers).size().is_constant() ||
      numeric_cast_v<uint64_t>(to_constant_expr(to_array_type(registers).size())) != 0x300)
    throw std::runtime_error("template must have registers[0x300] of unsigned bytes");
  const auto &ram = state.component_type("ram");
  if (ram.id() != ID_pointer || to_pointer_type(ram).base_type().id() != ID_unsignedbv ||
      to_unsignedbv_type(to_pointer_type(ram).base_type()).get_width() != 8)
    throw std::runtime_error("template RAM must be a pointer to unsigned bytes");
  for (const auto *name : {"ram_base", "ram_size", "return_address"}) {
    const auto &type = state.component_type(name);
    if (type.id() != ID_unsignedbv || to_unsignedbv_type(type).get_width() != 64)
      throw std::runtime_error(std::string("template needs a uint64_t field: ") + name);
  }
  Translator(model, instructions, listing, image, target, dispatch_branches, object_memory).run();
}
