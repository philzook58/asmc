#include "elf_image.h"
#include <elfio/elfio.hpp>
#include <limits>
#include <filesystem>
#include <stdexcept>
#include <map>
#include <set>

namespace {
std::string shell_quote(const std::string &value) {
  std::string result = "'";
  for (char c : value) result += c == '\'' ? "'\\''" : std::string(1, c);
  return result + "'";
}
}

ElfImage ElfImage::load(const std::string &path, const std::string &function,
                       std::optional<uint64_t> explicit_end, const std::vector<std::string> &callees,
                       const std::vector<std::string> &indirect_targets, bool rodata) {
  ELFIO::elfio elf;
  if (!elf.load(path)) throw std::runtime_error("cannot read ELF: " + path);
  bool riscv = elf.get_machine() == ELFIO::EM_RISCV;
  unsigned bits = elf.get_class() == ELFIO::ELFCLASS32 ? 32 : 64;
  if (elf.get_type() == ELFIO::ET_REL && (riscv || elf.get_machine() == ELFIO::EM_X86_64)) {
    auto linked = std::filesystem::path(path).replace_extension(".elf").string();
    auto linker = riscv ? "riscv64-unknown-elf-ld -m elf" + std::to_string(bits) + "lriscv" : "ld";
    throw std::runtime_error("relocatable ELF (.o) is not supported directly. Link it first:\n  " +
      linker + " -e " + shell_quote(function) + " " + shell_quote(path) + " -o " + shell_quote(linked) +
      "\nThen rerun ASMC on " + shell_quote(linked) + ". External data loading remains unsupported.");
  }
  if (elf.get_encoding() != ELFIO::ELFDATA2LSB || elf.get_type() != ELFIO::ET_EXEC ||
      (elf.get_class() != ELFIO::ELFCLASS32 && elf.get_class() != ELFIO::ELFCLASS64) ||
      (!riscv && (elf.get_machine() != ELFIO::EM_X86_64 || bits != 64)) ||
      (riscv && (elf.get_flags() & 8))) // RVE uses a different register/ABI subset.
    throw std::runtime_error("expected little-endian x86-64 or RV32/RV64 ET_EXEC (no RVE)");
  for (const auto &segment : elf.segments)
    if (segment->get_type() == ELFIO::PT_INTERP || segment->get_type() == ELFIO::PT_DYNAMIC)
      throw std::runtime_error("dynamic ELF loading is unsupported");
  std::set<std::string> wanted(callees.begin(), callees.end());
  wanted.insert(function);
  std::set<std::string> target_names;
  std::vector<uint64_t> target_addresses;
  for (const auto &target : indirect_targets) {
    if (!target.empty() && target[0] >= '0' && target[0] <= '9') {
      size_t used;
      auto address = std::stoull(target, &used, 0);
      if (used != target.size()) throw std::runtime_error("invalid indirect target: " + target);
      target_addresses.push_back(address);
    } else target_names.insert(target);
  }
  std::map<std::string, std::pair<uint64_t, uint64_t>> symbols_found;
  for (const auto &section : elf.sections) {
    if (section->get_type() != ELFIO::SHT_SYMTAB) continue;
    ELFIO::const_symbol_section_accessor symbols(elf, section.get());
    for (ELFIO::Elf_Xword i = 0; i < symbols.get_symbols_num(); ++i) {
      std::string name;
      ELFIO::Elf64_Addr value;
      ELFIO::Elf_Xword symbol_size;
      unsigned char bind, type, other;
      ELFIO::Elf_Half index;
      if (!symbols.get_symbol(i, name, value, symbol_size, bind, type, index, other))
        throw std::runtime_error("malformed ELF symbol table");
      if ((!wanted.count(name) && !target_names.count(name)) || index == ELFIO::SHN_UNDEF) continue;
      if (!symbols_found.emplace(name, std::make_pair(value, symbol_size)).second)
        throw std::runtime_error("ambiguous function symbol: " + name);
    }
  }
  ElfImage image{path, 0, {}, bits, riscv, {}, {}};
  for (const auto &name : wanted) {
    auto symbol = symbols_found.find(name);
    if (symbol == symbols_found.end()) throw std::runtime_error("function symbol not found: " + name);
    auto [start, size] = symbol->second;
    auto limit = name == function ? explicit_end : std::optional<uint64_t>{};
    std::string inferred_section;
    if (!limit && size == 0) {
      // A code window, not an inferred function boundary. Only reachable bytes
      // are decoded; reaching the window's end is still an error, not a return.
      for (const auto &section : elf.sections) {
        auto base = section->get_address(), length = section->get_size();
        if (section->get_type() != ELFIO::SHT_PROGBITS ||
            !(section->get_flags() & ELFIO::SHF_ALLOC) ||
            !(section->get_flags() & ELFIO::SHF_EXECINSTR) ||
            start < base || start - base >= length) continue;
        if (length > UINT64_MAX - base) throw std::runtime_error("executable section address range wraps");
        limit = base + length;
        inferred_section = section->get_name();
        break;
      }
      if (!limit)
        throw std::runtime_error("function " + name + " has no size or containing executable section; "
          "add .type/.size or use --lift-end-address for the entry");
      // Keep admitted windows disjoint when several unsized functions share a
      // section. Internal labels/indirect targets are not function boundaries.
      for (const auto &other : symbols_found)
        if (wanted.count(other.first) && other.second.first > start && other.second.first < *limit)
          limit = other.second.first;
    }
    if (!limit && size > UINT64_MAX - start) throw std::runtime_error("function address range wraps");
    uint64_t end = limit.value_or(start + size);
    if (bits == 32 && (start > UINT32_MAX || end > UINT64_C(0x100000000)))
      throw std::runtime_error("RV32 function address range wraps");
    if (end <= start || end - start > 16 * 1024 * 1024)
      throw std::runtime_error("invalid function range (maximum 16 MiB)");
    for (const auto &other : image.functions)
      if (start < other.end && other.begin < end)
        throw std::runtime_error("overlapping admitted function ranges");
    bool loaded = false;
    for (const auto &segment : elf.segments) {
      if (segment->get_type() != ELFIO::PT_LOAD || !(segment->get_flags() & ELFIO::PF_X)) continue;
      uint64_t base = segment->get_virtual_address(), length = segment->get_file_size();
      if (start < base || start - base > length || end - start > length - (start - base)) continue;
      const char *data = segment->get_data();
      if (!data) throw std::runtime_error("ELF code segment has no bytes");
      const auto *first = reinterpret_cast<const unsigned char *>(data) + (start - base);
      image.functions.push_back({name, start, end, {first, first + (end - start)}, inferred_section});
      loaded = true;
      break;
    }
    if (!loaded) throw std::runtime_error("function range is not in a file-backed executable segment: " + name);
    if (name == function) image.entry = start;
  }
  for (const auto &name : target_names) {
    auto found = symbols_found.find(name);
    if (found == symbols_found.end()) throw std::runtime_error("indirect target symbol not found: " + name);
    target_addresses.push_back(found->second.first);
  }
  for (auto address : target_addresses) {
    if (!image.function_at(address)) throw std::runtime_error("indirect target outside admitted functions");
    image.indirect_targets.push_back(address);
  }
  if (rodata) for (const auto &section : elf.sections) {
    if (section->get_name().rfind(".rodata", 0) != 0) continue;
    if (!(section->get_flags() & ELFIO::SHF_ALLOC) ||
        (section->get_flags() & (ELFIO::SHF_WRITE | ELFIO::SHF_EXECINSTR)) ||
        section->get_type() != ELFIO::SHT_PROGBITS)
      throw std::runtime_error("expected allocated read-only .rodata section");
    auto size = section->get_size(), start = section->get_address();
    if (!size) continue;
    if (size > 65536 || size > UINT64_MAX - start ||
        (bits == 32 && start + size > UINT64_C(0x100000000)))
      throw std::runtime_error("invalid .rodata range (maximum 64 KiB per section)");
    const unsigned char *bytes = nullptr;
    for (const auto &segment : elf.segments) {
      auto base = segment->get_virtual_address(), length = segment->get_file_size();
      if (segment->get_type() == ELFIO::PT_LOAD && (segment->get_flags() & ELFIO::PF_R) &&
          !(segment->get_flags() & ELFIO::PF_W) && start >= base &&
          start - base <= length && size <= length - (start - base)) {
        const auto *data = segment->get_data();
        if (data) bytes = reinterpret_cast<const unsigned char *>(data) + (start - base);
      }
    }
    if (!bytes) throw std::runtime_error(".rodata is not in a read-only file-backed ELF segment");
    for (const auto &other : image.readonly)
      if (start < other.begin + other.bytes.size() && other.begin < start + size)
        throw std::runtime_error("overlapping .rodata sections");
    image.readonly.push_back({start, {bytes, bytes + size}});
  }
  return image;
}

const FunctionImage *ElfImage::function_at(uint64_t address) const {
  for (const auto &function : functions)
    if (address >= function.begin && address < function.end) return &function;
  return nullptr;
}
