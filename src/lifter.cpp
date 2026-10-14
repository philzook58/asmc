#include "lifter.h"
#include <ghidra/context.hh>
#include <ghidra/loadimage.hh>
#include <ghidra/marshal.hh>
#include <ghidra/pcoderaw.hh>
#include <ghidra/sleigh.hh>
#include <ghidra/xml.hh>
#include <fstream>
#include <queue>
#include <sstream>
#include <stdexcept>

namespace {
class CodeImage : public ghidra::LoadImage {
  const ElfImage &image;
public:
  explicit CodeImage(const ElfImage &image) : LoadImage(image.path), image(image) {}
  void loadFill(unsigned char *out, int size, const ghidra::Address &address) override {
    auto start = address.getOffset();
    const auto *function = image.function_at(start);
    // SLEIGH reads ahead in its decoder. Pad that lookahead, then separately
    // reject instructions whose actual decoded length exceeds the input.
    for (int i = 0; i < size; ++i) {
      auto pos = start + static_cast<uint64_t>(i);
      out[i] = function && pos >= function->begin && pos < function->end ? function->bytes[pos - function->begin] : 0;
    }
  }
  std::string getArchType() const override {
    return image.riscv ? "RISCV:LE:" + std::to_string(image.address_bits) + ":default" : "x86:LE:64:default";
  }
  void adjustVma(long) override {}
};
Varnode copy_node(const ghidra::VarnodeData &n) {
  auto name = n.space->getName();
  Space space = name == "const" ? Space::constant : name == "register" ? Space::reg :
                name == "unique" ? Space::unique : name == "ram" ? Space::ram : Space::other;
  return {space, n.offset, static_cast<unsigned>(n.size)};
}
class Capture : public ghidra::PcodeEmit {
public:
  std::vector<PcodeOp> ops;
  void dump(const ghidra::Address &, ghidra::OpCode opcode, ghidra::VarnodeData *out,
            ghidra::VarnodeData *inputs, int count) override {
    PcodeOp op{opcode, {}, {}, ""};
    if (out) op.output = copy_node(*out);
    for (int i = 0; i < count; ++i) op.inputs.push_back(copy_node(inputs[i]));
    if (opcode == ghidra::CPUI_LOAD || opcode == ghidra::CPUI_STORE)
      op.memory_space = inputs[0].getSpaceFromConst()->getName();
    ops.push_back(std::move(op));
  }
};
class Assembly : public ghidra::AssemblyEmit {
public:
  std::string text;
  void dump(const ghidra::Address &, const std::string &mnemonic, const std::string &body) override {
    text = mnemonic + " " + body;
  }
};
}

int64_t relative_offset(const Varnode &n) {
  if (n.size == 0 || n.size > 8) throw std::runtime_error("invalid relative branch width");
  unsigned bits = n.size * 8;
  uint64_t value = n.offset;
  if (bits < 64) {
    uint64_t mask = (UINT64_C(1) << bits) - 1;
    value &= mask;
    if (value & (UINT64_C(1) << (bits - 1))) value |= ~mask;
  }
  // Avoid an implementation-defined out-of-range unsigned-to-signed cast.
  return value <= INT64_MAX ? static_cast<int64_t>(value) : -1 - static_cast<int64_t>(~value);
}
size_t relative_target(const Instruction &insn, size_t index, const Varnode &node) {
  auto delta = relative_offset(node);
  auto target = static_cast<int64_t>(index) + delta;
  if (target < 0 || static_cast<uint64_t>(target) > insn.ops.size())
    throw std::runtime_error(describe(insn, index) + ": invalid relative p-code branch");
  return static_cast<size_t>(target);
}

std::string describe(const Instruction &insn, size_t index) {
  std::ostringstream s;
  s << "0x" << std::hex << insn.address << std::dec << " pcode[" << index << "] " << insn.assembly;
  if (index < insn.ops.size()) s << " (" << ghidra::get_opname(insn.ops[index].opcode) << ")";
  return s.str();
}

Instructions lift(const ElfImage &image, const std::string &sla, const std::string &pspec) {
  ghidra::AttributeId::initialize();
  ghidra::ElementId::initialize();
  CodeImage loader(image);
  ghidra::ContextInternal context;
  ghidra::Sleigh engine(&loader, &context);
  ghidra::DocumentStorage storage;
  std::istringstream config("<sleigh>" + sla + "</sleigh>");
  storage.registerTag(storage.parseDocument(config)->getRoot());
  storage.registerTag(storage.openDocument(pspec)->getRoot());
  engine.initialize(storage);
  engine.allowContextSet(false);
  const auto *processor = storage.getTag("processor_spec");
  ghidra::XmlDecode decoder(&engine, processor);
  auto root = decoder.openElement();
  while (auto child = decoder.peekElement()) {
    if (child == ghidra::ELEM_CONTEXT_DATA) { context.decodeFromSpec(decoder); break; }
    decoder.openElement(); decoder.closeElementSkipping(child);
  }
  decoder.closeElement(root);
  // Refuse a spec with a different register layout from the C header.
  const std::pair<const char *, uint64_t> expected[] = {
    {"RAX",0}, {"RCX",8}, {"RDX",16}, {"RBX",24}, {"RSP",32}, {"RBP",40},
    {"RSI",48}, {"RDI",56}, {"R8",128}, {"R9",136}, {"R10",144}, {"R11",152},
    {"R12",160}, {"R13",168}, {"R14",176}, {"R15",184}, {"RIP",0x288},
    {"CF",0x200}, {"PF",0x202}, {"AF",0x204}, {"ZF",0x206}, {"SF",0x207},
    {"DF",0x20a}, {"OF",0x20b}
  };
  if (image.riscv) {
    const char *names[] = {"zero","ra","sp","gp","tp","t0","t1","t2","s0","s1",
      "a0","a1","a2","a3","a4","a5","a6","a7","s2","s3","s4","s5","s6","s7","s8","s9","s10","s11","t3","t4","t5","t6"};
    for (unsigned i = 0; i < 32; ++i) {
      auto reg = engine.getRegister(names[i]);
      if (reg.offset != 0x2000 + i * image.address_bits / 8 || reg.size != image.address_bits / 8)
        throw std::runtime_error("SLEIGH/RISC-V register layout mismatch");
    }
  } else for (const auto &[name, offset] : expected)
    if (engine.getRegister(name).offset != offset)
      throw std::runtime_error(std::string("SLEIGH/C register layout mismatch: ") + name);

  Instructions result;
  std::queue<uint64_t> pending;
  pending.push(image.entry);
  for (auto destination : image.indirect_targets) pending.push(destination);
  auto enqueue = [&](uint64_t address) {
    if (!image.function_at(address)) {
      std::ostringstream error;
      error << "control flow leaves admitted lifting ranges at 0x" << std::hex << address
            << "; check --lift-end-address/ELF size, or use --callee NAME to admit another function";
      throw std::runtime_error(error.str());
    }
    pending.push(address);
  };
  while (!pending.empty()) {
    auto pc = pending.front(); pending.pop();
    if (result.count(pc)) continue;
    ghidra::Address address(engine.getDefaultCodeSpace(), pc);
    Capture capture;
    Assembly assembly;
    int length = engine.oneInstruction(capture, address);
    engine.printAssembly(assembly, address);
    if (length <= 0 || static_cast<uint64_t>(length) > image.function_at(pc)->end - pc)
      throw std::runtime_error("instruction extends beyond the selected lifting window");
    Instruction insn{pc, static_cast<unsigned>(length), assembly.text, std::move(capture.ops), {}};
    auto next = result.lower_bound(pc);
    if ((next != result.end() && pc + length > next->first) ||
        (next != result.begin() && std::prev(next)->first + std::prev(next)->second.length > pc))
      throw std::runtime_error("overlapping instruction encodings are unsupported");

    // Walk the p-code CFG, so dead operations and dead machine bytes are not
    // accidentally translated. Both edges of a conditional remain feasible.
    std::queue<size_t> ops;
    ops.push(0);
    while (!ops.empty()) {
      auto i = ops.front(); ops.pop();
      if (!insn.reachable.insert(i).second) continue;
      if (i == insn.ops.size()) { enqueue(pc + length); continue; }
      const auto &op = insn.ops[i];
      if (op.opcode == ghidra::CPUI_RETURN) continue;
      if (op.opcode == ghidra::CPUI_BRANCH || op.opcode == ghidra::CPUI_CBRANCH) {
        const auto &target = op.inputs.at(0);
        if (target.space == Space::constant) ops.push(relative_target(insn, i, target));
        else if (target.space == Space::ram) enqueue(target.offset);
        else throw std::runtime_error(describe(insn, i) + ": unsupported branch space");
        if (op.opcode == ghidra::CPUI_CBRANCH) ops.push(i + 1);
      } else if (op.opcode == ghidra::CPUI_CALL) {
        const auto &destination = op.inputs.at(0);
        const auto *callee = image.function_at(destination.offset);
        if (destination.space != Space::ram || !callee || callee->begin != destination.offset)
          throw std::runtime_error(describe(insn, i) + ": CALL must target an admitted function entry; use --callee NAME");
        // Only architectures whose raw call ends the instruction are supported.
        if (i + 1 != insn.ops.size())
          throw std::runtime_error(describe(insn, i) + ": operations after CALL are unsupported");
        enqueue(destination.offset);
        enqueue(pc + length); // Native return address, not an extra modeled call stack.
      } else if (op.opcode == ghidra::CPUI_BRANCHIND) {
        if (image.indirect_targets.empty())
          throw std::runtime_error(describe(insn, i) + ": indirect jump needs --indirect-target SYMBOL_OR_ADDRESS (repeatable)");
        for (auto destination : image.indirect_targets) enqueue(destination);
      } else if (op.opcode == ghidra::CPUI_CALLIND) {
        throw std::runtime_error(describe(insn, i) + ": unsupported control-flow operation");
      } else ops.push(i + 1);
    }
    result.emplace(pc, std::move(insn));
  }
  return result;
}

void write_listing(const Instructions &instructions, const std::string &path) {
  std::ofstream out(path);
  if (!out) throw std::runtime_error("cannot write assembly listing: " + path);
  for (const auto &[address, insn] : instructions)
    for (auto i : insn.reachable) out << describe(insn, i) << '\n';
  if (!out) throw std::runtime_error("failed to write assembly listing: " + path);
}
