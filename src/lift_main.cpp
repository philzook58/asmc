#include "elf_image.h"
#include "lifter.h"
#include "translate.h"
#include <goto-programs/read_goto_binary.h>
#include <goto-programs/write_goto_binary.h>
#include <util/config.h>
#include <util/cmdline.h>
#include <util/message.h>
#include <util/version.h>
#include <ghidra/error.hh>
#include <ghidra/xml.hh>
#include <sleigh/libconfig.h>
#include <iostream>
#include <stdexcept>
#include <vector>

int main(int argc, char **argv) {
  try {
    if (argc == 2 && std::string(argv[1]) == "--version") {
      std::cout << "ASMC-lift 0.1.0; CBMC " << CBMC_VERSION << "; Ghidra " << sleigh_VERSION << '\n';
      return 0;
    }
    if (argc == 1 || (argc == 2 && std::string(argv[1]) == "--help")) {
      std::cout << "Lift ELF instructions to a GOTO object (does not verify):\n"
                   "  asmc-lift FILE.elf --function NAME --template SEED.gb -o OUT.gb\n"
                   "       [--target GOTO_NAME] [--callee NAME] [--end-address ADDRESS]\n"
                   "       [--sla FILE] [--pspec FILE] [--memory ram|objects] [--rodata]\n"
                   "       [--indirect-target SYMBOL_OR_ADDRESS] [--dispatch]\n\n"
                   "  Compile SEED.gb from runtime/runtime.c with goto-cc -I include -c.\n"
                   "  For --memory objects, compile the runtime with -DASMC_OBJECT_MEMORY.\n"
                   "  Architecture is selected from ELF; use -m32 for an RV32 template.\n"
                   "  Outputs OUT.gb and its address/p-code listing OUT.gb.asm.\n"
                   "  Use 'asmc --help' for the top-level verification driver.\n";
      return argc == 1 ? 2 : 0;
    }
    std::string elf = argv[1], function, seed, output, target = "asmc_target";
    std::string sla, pspec;
    std::optional<uint64_t> end;
    std::vector<std::string> callees, indirect_targets;
    bool rodata = false, object_memory = false;
    bool dispatch = false;
    for (int i = 2; i < argc; ++i) {
      std::string key = argv[i];
      if (key == "--rodata") { rodata = true; continue; }
      if (key == "--dispatch") { dispatch = true; continue; }
      if (++i == argc) throw std::runtime_error("option has no value: " + key);
      std::string value = argv[i];
      if (key == "--function") function = value;
      else if (key == "--target") target = value;
      else if (key == "--callee") callees.push_back(value);
      else if (key == "--indirect-target") indirect_targets.push_back(value);
      else if (key == "--template") seed = value;
      else if (key == "-o") output = value;
      else if (key == "--memory") {
        if (value != "ram" && value != "objects") throw std::runtime_error("--memory must be ram or objects");
        object_memory = value == "objects";
      }
      else if (key == "--sla") sla = value;
      else if (key == "--pspec") pspec = value;
      else if (key == "--end-address") {
        size_t used;
        end = std::stoull(value, &used, 0);
        if (used != value.size()) throw std::runtime_error("invalid end address");
      } else throw std::runtime_error("unknown option: " + key);
    }
    if (function.empty() || seed.empty() || output.empty())
      throw std::runtime_error("--function, --template and -o are required");
    if (object_memory && rodata)
      throw std::runtime_error("--memory objects cannot be combined with --rodata; no ELF data fallback");
    auto image = ElfImage::load(elf, function, end, callees, indirect_targets, rodata);
    auto directory = std::string(ASMC_SPEC_DIR) + (image.riscv ? "/RISCV" : "/x86") + "/data/languages/";
    if (sla.empty()) sla = directory + (image.riscv ? (image.address_bits == 32 ? "riscv.ilp32d.sla" : "riscv.lp64d.sla") : "x86-64.sla");
    if (pspec.empty()) pspec = directory + (image.riscv ? (image.address_bits == 32 ? "RV32.pspec" : "RV64.pspec") : "x86-64.pspec");
    auto instructions = lift(image, sla, pspec);
    bool reads_af = false;
    if (!image.riscv) for (const auto &[address, instruction] : instructions)
      for (auto index : instruction.reachable) if (index < instruction.ops.size())
        for (const auto &input : instruction.ops[index].inputs)
          if (input.space == Space::reg && input.offset <= 0x204 &&
              input.offset + input.size > 0x204) reads_af = true;
    if (reads_af)
      std::cerr << "ASMC warning: x86 AF is read, but pinned SLEIGH does not update it for arithmetic; "
                   "checks observing auxiliary carry may disagree with hardware.\n";
    stream_message_handlert messages(std::cerr);
    // Set C dialect and OS defaults before importing target architecture
    // settings; config's default constructor leaves the dialect unset.
    cmdlinet defaults;
    config.set(defaults);
    auto model = read_goto_binary(seed, messages);
    if (!model) throw std::runtime_error("cannot read GOTO template");
    config.set_from_symbol_table(model->symbol_table);
    if (config.ansi_c.pointer_width != image.address_bits || config.ansi_c.endianness != configt::ansi_ct::endiannesst::IS_LITTLE_ENDIAN)
      throw std::runtime_error("template must use the ELF's pointer width and little endianness");
    auto listing = output + ".asm";
    translate(*model, instructions, listing, image, target, dispatch, object_memory);
    // Only publish a GOTO object after the entire function has translated.
    write_listing(instructions, listing);
    if (write_goto_binary(output, *model, messages)) throw std::runtime_error("cannot write GOTO object");
    std::cout << "Lifted " << instructions.size() << " instructions from " << function << " to " << output << '\n';
    return 0;
  } catch (const ghidra::DecoderError &error) {
    std::cerr << "ASMC decoder: " << error.explain << '\n';
  } catch (const ghidra::LowlevelError &error) {
    std::cerr << "ASMC: " << error.explain << '\n';
  } catch (const std::exception &error) {
    std::cerr << "ASMC: " << error.what() << '\n';
  }
  return 2;
}
