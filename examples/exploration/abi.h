/* Example-local names keep the same harness usable on x86-64 and RISC-V. */
#ifdef ASMC_RISCV_XLEN
#include "asmc_riscv.h"
#define frame_type asmc_riscv_frame
#define enter(s, ram, size) asmc_riscv_setup_ram_model_at(s, ram, 0x1000, size, 0x1000 + size - 16)
#define arg(s, i, value) asmc_riscv_arg(s, i, value)
#define arg32(s, i, value) asmc_riscv_arg32(s, i, value)
#define result(s) asmc_riscv_result(s)
#define abi_check asmc_riscv_check
#else
#include "asmc_x86.h"
#define frame_type asmc_sysv_frame
#define enter(s, ram, size) asmc_sysv_setup_ram_model(s, ram, 0x1000, size)
#define arg(s, i, value) asmc_sysv_arg64(s, i, value)
#define arg32(s, i, value) asmc_sysv_arg32(s, i, value)
#define result(s) asmc_sysv_result64(s)
#define abi_check asmc_sysv_check
#endif
