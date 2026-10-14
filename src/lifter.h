#pragma once
#include "elf_image.h"
#include <ghidra/opcodes.hh>
#include <map>
#include <optional>
#include <set>

enum class Space { constant, reg, unique, ram, other };
struct Varnode {
  Space space;
  uint64_t offset;
  unsigned size;
};
struct PcodeOp {
  ghidra::OpCode opcode;
  std::optional<Varnode> output;
  std::vector<Varnode> inputs;
  std::string memory_space;
};
struct Instruction {
  uint64_t address;
  unsigned length;
  std::string assembly;
  std::vector<PcodeOp> ops;
  std::set<size_t> reachable;
};
using Instructions = std::map<uint64_t, Instruction>;

int64_t relative_offset(const Varnode &node);
size_t relative_target(const Instruction &instruction, size_t index, const Varnode &node);
Instructions lift(const ElfImage &image, const std::string &sla, const std::string &pspec);
std::string describe(const Instruction &instruction, size_t index);
void write_listing(const Instructions &instructions, const std::string &path);
