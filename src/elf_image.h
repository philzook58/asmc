#pragma once
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

struct FunctionImage {
  std::string name;
  uint64_t begin, end;
  std::vector<unsigned char> bytes;
  std::string inferred_section;
};
struct ReadOnlyImage {
  uint64_t begin;
  std::vector<unsigned char> bytes;
};
struct ElfImage {
  std::string path;
  uint64_t entry;
  std::vector<FunctionImage> functions;
  unsigned address_bits = 64;
  bool riscv = false;
  std::vector<uint64_t> indirect_targets;
  std::vector<ReadOnlyImage> readonly;
  const FunctionImage *function_at(uint64_t address) const;
  static ElfImage load(const std::string &path, const std::string &function,
                       std::optional<uint64_t> end, const std::vector<std::string> &callees,
                       const std::vector<std::string> &indirect_targets = {}, bool rodata = false);
};
