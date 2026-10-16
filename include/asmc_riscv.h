#ifndef ASMC_RISCV_H
#define ASMC_RISCV_H
#include "asmc_state.h"
#include <assert.h>

/* asmc defines this from ELF. For manual goto-cc use -DASMC_RISCV_XLEN=32/64. */
#if ASMC_RISCV_XLEN != 32 && ASMC_RISCV_XLEN != 64
#error "ASMC_RISCV_XLEN must be 32 or 64"
#endif
#define ASMC_RV_BYTES (ASMC_RISCV_XLEN / 8)
/* The translator maps SLEIGH's GPR bank to x0..x31 at XLEN-byte strides. */
static inline uint64_t asmc_riscv_reg(const struct asmc_state *s, unsigned reg) {
  assert(reg < 32);
  return asmc_get_reg(s, reg * ASMC_RV_BYTES, ASMC_RV_BYTES);
}
static inline void asmc_riscv_set(struct asmc_state *s, unsigned reg, uint64_t value) {
  assert(reg < 32 && (reg != 0 || value == 0));
  asmc_set_reg(s, reg * ASMC_RV_BYTES, ASMC_RV_BYTES, value);
}
static inline void asmc_riscv_arg(struct asmc_state *s, unsigned index, uint64_t value) {
  assert(index < 8);
  asmc_riscv_set(s, 10 + index, value);
}
static inline void asmc_riscv_arg32(struct asmc_state *s, unsigned index, uint32_t value) {
  /* RV64 sign-extends even uint32_t arguments, as required by the psABI. */
  asmc_riscv_arg(s, index, (uint64_t)(int64_t)(int32_t)value);
}
static inline uint64_t asmc_riscv_result(const struct asmc_state *s) {
  return asmc_riscv_reg(s, 10);
}
static const unsigned asmc_riscv_preserved[] = {2,3,4,8,9,18,19,20,21,22,23,24,25,26,27};
struct asmc_riscv_frame { uint64_t preserved[15]; };
static inline struct asmc_riscv_frame asmc_riscv_setup_ram_model_at(
    struct asmc_state *s, uint8_t *ram, uint64_t base, uint64_t size, uint64_t sp) {
  uint64_t maximum = ASMC_RISCV_XLEN == 32 ? UINT32_MAX : UINT64_MAX;
  assert(base <= maximum && size <= maximum - base);
  assert((sp & 15) == 0 && sp >= base && sp - base <= size && sp <= maximum);
  s->ram = ram; s->ram_base = base; s->ram_size = size;
  s->return_address = UINT64_C(0x7fff0000);
  asmc_riscv_set(s, 0, 0);
  asmc_riscv_set(s, 1, s->return_address);
  asmc_riscv_set(s, 2, sp);
  struct asmc_riscv_frame frame;
  for (unsigned i = 0; i < 15; ++i)
    frame.preserved[i] = asmc_riscv_reg(s, asmc_riscv_preserved[i]);
  return frame;
}
static inline void asmc_riscv_check(const struct asmc_state *s, const struct asmc_riscv_frame *frame) {
#define ASMC_CHECK_SAVED(reg, name, index) \
  __CPROVER_assert(asmc_riscv_reg(s, reg) == frame->preserved[index], \
                   "ABI violation: " name " was not restored")
  ASMC_CHECK_SAVED(2, "stack pointer sp (x2)", 0);
  ASMC_CHECK_SAVED(3, "register gp (x3)", 1);
  ASMC_CHECK_SAVED(4, "register tp (x4)", 2);
  ASMC_CHECK_SAVED(8, "callee-saved register s0 (x8)", 3);
  ASMC_CHECK_SAVED(9, "callee-saved register s1 (x9)", 4);
  ASMC_CHECK_SAVED(18, "callee-saved register s2 (x18)", 5);
  ASMC_CHECK_SAVED(19, "callee-saved register s3 (x19)", 6);
  ASMC_CHECK_SAVED(20, "callee-saved register s4 (x20)", 7);
  ASMC_CHECK_SAVED(21, "callee-saved register s5 (x21)", 8);
  ASMC_CHECK_SAVED(22, "callee-saved register s6 (x22)", 9);
  ASMC_CHECK_SAVED(23, "callee-saved register s7 (x23)", 10);
  ASMC_CHECK_SAVED(24, "callee-saved register s8 (x24)", 11);
  ASMC_CHECK_SAVED(25, "callee-saved register s9 (x25)", 12);
  ASMC_CHECK_SAVED(26, "callee-saved register s10 (x26)", 13);
  ASMC_CHECK_SAVED(27, "callee-saved register s11 (x27)", 14);
#undef ASMC_CHECK_SAVED
  __CPROVER_assert(asmc_riscv_reg(s, 0) == 0, "ABI violation: zero register x0 must remain zero");
}

/* Choose the highest aligned entry SP in the supplied RAM region. */
static inline struct asmc_riscv_frame asmc_riscv_setup_ram_model(
    struct asmc_state *s, uint8_t *ram, uint64_t base, uint64_t size) {
  uint64_t maximum = ASMC_RISCV_XLEN == 32 ? UINT32_MAX : UINT64_MAX;
  assert(size >= 16 && base <= maximum && size <= maximum - base);
  return asmc_riscv_setup_ram_model_at(s, ram, base, size, (base + size) & ~UINT64_C(15));
}

/* Set arguments first. Setup preserves argument registers and RAM contents. */
static inline void asmc_riscv_call_ram_model(
    struct asmc_state *s, uint8_t *ram, uint64_t base, uint64_t size) {
  struct asmc_riscv_frame saved_abi = asmc_riscv_setup_ram_model(s, ram, base, size);
  ASMC_TARGET(s);
  asmc_riscv_check(s, &saved_abi);
}

#ifdef ASMC_OBJECT_MEMORY
static inline void asmc_riscv_arg_ptr(struct asmc_state *s, unsigned index, const void *p) {
  asmc_riscv_arg(s, index, (uintptr_t)p);
}
static inline void *asmc_riscv_result_ptr(const struct asmc_state *s) {
  /* Keep the narrowing step explicit for CBMC 6.11's SMT pointer-cast bug.
     Fix: philzook58/cbmc, branch fix/smt2-integer-pointer-width. */
  uintptr_t address = (uintptr_t)asmc_riscv_result(s);
  return (void *)address;
}
static inline struct asmc_riscv_frame asmc_riscv_setup_objects_model(
    struct asmc_state *s, uint8_t *stack, uint64_t size) {
  assert(__CPROVER_w_ok(stack, size));
  return asmc_riscv_setup_ram_model(s, stack, (uintptr_t)stack, size);
}
/* Setup, execute, and assert scalar ABI obligations using a C stack object. */
static inline void asmc_riscv_call_objects_model(
    struct asmc_state *s, uint8_t *stack, uint64_t size) {
  struct asmc_riscv_frame saved_abi = asmc_riscv_setup_objects_model(s, stack, size);
  ASMC_TARGET(s);
  asmc_riscv_check(s, &saved_abi);
}

#endif
#endif
