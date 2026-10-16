#ifndef ASMC_X86_H
#define ASMC_X86_H
#include "asmc_state.h"
#include <stdbool.h>
#include <assert.h>

/* Offsets from the pinned x86-64 SLEIGH register space, not an ABI guess. */
enum asmc_register {
  ASMC_RAX = 0x00, ASMC_RCX = 0x08, ASMC_RDX = 0x10, ASMC_RBX = 0x18,
  ASMC_RSP = 0x20, ASMC_RBP = 0x28, ASMC_RSI = 0x30, ASMC_RDI = 0x38,
  ASMC_R8 = 0x80, ASMC_R9 = 0x88, ASMC_R10 = 0x90, ASMC_R11 = 0x98,
  ASMC_R12 = 0xa0, ASMC_R13 = 0xa8, ASMC_R14 = 0xb0, ASMC_R15 = 0xb8,
  ASMC_CF = 0x200, ASMC_PF = 0x202, ASMC_AF = 0x204, ASMC_ZF = 0x206,
  ASMC_SF = 0x207, ASMC_DF = 0x20a, ASMC_OF = 0x20b, ASMC_RIP = 0x288
};
#define ASMC_RETURN_ADDRESS UINT64_C(0x7fffffff0000)

struct asmc_sysv_frame {
  uint64_t preserved[6];
  uint64_t stack_pointer;
};

/* Integer-only SysV arguments 0..5. Machine addresses stay numeric. */
static inline unsigned asmc_sysv_arg_register(unsigned index) {
  const unsigned registers[] = {ASMC_RDI, ASMC_RSI, ASMC_RDX, ASMC_RCX, ASMC_R8, ASMC_R9};
  assert(index < 6);
  return registers[index];
}
static inline void asmc_sysv_arg64(struct asmc_state *s, unsigned index, uint64_t value) {
  asmc_set_reg(s, asmc_sysv_arg_register(index), 8, value);
}
static inline void asmc_sysv_arg32(struct asmc_state *s, unsigned index, uint32_t value) {
  /* Initialize only the declared value bits; excess bits stay arbitrary. */
  asmc_set_reg(s, asmc_sysv_arg_register(index), 4, value);
}
static inline uint64_t asmc_sysv_result64(const struct asmc_state *s) {
  return asmc_get_reg(s, ASMC_RAX, 8);
}
static inline uint32_t asmc_sysv_result32(const struct asmc_state *s) {
  return (uint32_t)asmc_get_reg(s, ASMC_RAX, 4);
}
static inline bool asmc_sysv_result_bool(const struct asmc_state *s) {
  uint64_t value = asmc_get_reg(s, ASMC_RAX, 1);
  assert(value <= 1); /* SysV _Bool results have zero bits 1..7. */
  return value != 0;
}
static inline void asmc_setup_stack(struct asmc_state *s, uint64_t sp) {
  s->return_address = ASMC_RETURN_ADDRESS;
  asmc_set_reg(s, ASMC_RSP, 8, sp);
  asmc_store(s, sp, 8, s->return_address);
}
static inline void asmc_assume_flags(const struct asmc_state *s) {
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_CF) <= 1);
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_PF) <= 1);
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_AF) <= 1);
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_ZF) <= 1);
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_SF) <= 1);
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_OF) <= 1);
  __CPROVER_assume(ASMC_REG_BYTE(s, ASMC_DF) <= 1);
}
static const unsigned asmc_sysv_preserved[] = {
  ASMC_RBX, ASMC_RBP, ASMC_R12, ASMC_R13, ASMC_R14, ASMC_R15
};
static inline struct asmc_sysv_frame asmc_sysv_setup_ram_model_at(struct asmc_state *s, uint8_t *ram,
                                     uint64_t base, uint64_t size, uint64_t sp) {
  /* Other registers and RAM retain their initial values. */
  assert((sp & 15) == 8); /* Stack alignment at function entry, after CALL. */
  s->ram = ram;
  s->ram_base = base;
  s->ram_size = size;
  asmc_assume_flags(s);
  asmc_set_reg(s, ASMC_DF, 1, 0);
  asmc_setup_stack(s, sp);
  struct asmc_sysv_frame frame;
  frame.stack_pointer = sp;
  for (unsigned i = 0; i < 6; ++i)
    frame.preserved[i] = asmc_get_reg(s, asmc_sysv_preserved[i], 8);
  return frame;
}
static inline void asmc_sysv_check(const struct asmc_state *s, const struct asmc_sysv_frame *frame) {
  __CPROVER_assert(asmc_get_reg(s, ASMC_RSP, 8) == frame->stack_pointer + 8,
                   "ABI violation: RSP was not restored after return");
  __CPROVER_assert(asmc_get_reg(s, ASMC_DF, 1) == 0,
                   "ABI violation: direction flag DF must be clear on return");
  /* Literal register names keep counterexamples useful, including custom harnesses. */
#define ASMC_CHECK_SAVED(reg, index) \
  __CPROVER_assert(asmc_get_reg(s, ASMC_##reg, 8) == frame->preserved[index], \
                   "ABI violation: callee-saved register " #reg " was not restored")
  ASMC_CHECK_SAVED(RBX, 0);
  ASMC_CHECK_SAVED(RBP, 1);
  ASMC_CHECK_SAVED(R12, 2);
  ASMC_CHECK_SAVED(R13, 3);
  ASMC_CHECK_SAVED(R14, 4);
  ASMC_CHECK_SAVED(R15, 5);
#undef ASMC_CHECK_SAVED
}

/* Highest valid SysV entry SP in RAM; addresses and capacity remain explicit. */
static inline struct asmc_sysv_frame asmc_sysv_setup_ram_model(
    struct asmc_state *s, uint8_t *ram, uint64_t base, uint64_t size) {
  assert(size >= 16 && size <= UINT64_MAX - base);
  uint64_t sp = ((base + size - 16) & ~UINT64_C(15)) + 8;
  assert(sp >= base);
  return asmc_sysv_setup_ram_model_at(s, ram, base, size, sp);
}

/* Set arguments first. Setup preserves them and writes the stack return sentinel. */
static inline void asmc_sysv_call_ram_model(
    struct asmc_state *s, uint8_t *ram, uint64_t base, uint64_t size) {
  struct asmc_sysv_frame saved_abi = asmc_sysv_setup_ram_model(s, ram, base, size);
  ASMC_TARGET(s);
  asmc_sysv_check(s, &saved_abi);
}

#ifdef ASMC_OBJECT_MEMORY
/* These addresses are CBMC pointer encodings, not physical machine addresses. */
static inline void asmc_sysv_arg_ptr(struct asmc_state *s, unsigned index, const void *p) {
  asmc_sysv_arg64(s, index, (uintptr_t)p);
}
static inline void *asmc_sysv_result_ptr(const struct asmc_state *s) {
  return (void *)(uintptr_t)asmc_sysv_result64(s);
}
static inline struct asmc_sysv_frame asmc_sysv_setup_objects_model(
    struct asmc_state *s, uint8_t *stack, uint64_t size) {
  assert(__CPROVER_w_ok(stack, size));
  return asmc_sysv_setup_ram_model(s, stack, (uintptr_t)stack, size);
}
/* Setup, execute, and assert scalar ABI obligations using a C stack object. */
static inline void asmc_sysv_call_objects_model(
    struct asmc_state *s, uint8_t *stack, uint64_t size) {
  struct asmc_sysv_frame saved_abi = asmc_sysv_setup_objects_model(s, stack, size);
  ASMC_TARGET(s);
  asmc_sysv_check(s, &saved_abi);
}

#endif
#endif
