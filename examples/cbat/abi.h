/* Private aliases for the same C comparisons on all three scalar ABIs. */
#ifdef ASMC_RISCV_XLEN
#include "asmc_riscv.h"
typedef struct asmc_riscv_frame frame_t;
#define arg32 asmc_riscv_arg32
#define arg_ptr asmc_riscv_arg_ptr
#define result asmc_riscv_result
#define check_frame asmc_riscv_check
#define enter_objects asmc_riscv_enter_objects
static inline frame_t enter_ram(struct asmc_state *s, uint8_t *ram, unsigned size) {
  return asmc_riscv_enter(s, ram, 0x1000, size, (0x1000 + size) & ~UINT64_C(15));
}
#else
#include "asmc_x86.h"
typedef struct asmc_sysv_frame frame_t;
#define arg32 asmc_sysv_arg32
#define arg_ptr asmc_sysv_arg_ptr
#define result asmc_sysv_result64
#define check_frame asmc_sysv_check
#define enter_objects asmc_sysv_enter_objects
static inline frame_t enter_ram(struct asmc_state *s, uint8_t *ram, unsigned size) {
  return asmc_sysv_enter_at_end(s, ram, 0x1000, size);
}
#endif

static inline uint8_t result_bool(const struct asmc_state *s) {
  uint8_t value = (uint8_t)result(s);
  assert(value <= 1); /* Compare the declared _Bool result bits. */
  return value;
}
