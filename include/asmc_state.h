#ifndef ASMC_STATE_H
#define ASMC_STATE_H
#include <stdint.h>

#define ASMC_REGISTER_BYTES 0x300

#ifdef ASMC_SCALAR_REGISTERS
/* Flat arrays also work with CBMC's SMT encoders; avoid arrays of arrays. */
struct asmc_register_bank {
  uint64_t block0[32], block1[32], block2[32];
};
#define ASMC_REG_WORD(s, offset) (*((offset) < 256 ? &(s)->registers.block0[(offset) / 8] : \
  (offset) < 512 ? &(s)->registers.block1[((offset) - 256) / 8] : \
                 &(s)->registers.block2[((offset) - 512) / 8]))
#endif

struct asmc_state {
#ifdef ASMC_SCALAR_REGISTERS
  /* 96 storage cells, not architectural registers; byte offsets stay the same. */
  struct asmc_register_bank registers;
#else
  uint8_t registers[ASMC_REGISTER_BYTES];
#endif
  uint8_t *ram;
  uint64_t ram_base;
  uint64_t ram_size;
  uint64_t return_address;
};

/* Shared byte addressing preserves every overlapping SLEIGH varnode, including
   accesses spanning blocks. Use this lvalue instead of indexing registers. */
#ifdef ASMC_SCALAR_REGISTERS
#define ASMC_REG_BYTE(s, offset) (((uint8_t *)&ASMC_REG_WORD(s, offset))[(offset) % 8])
#else
#define ASMC_REG_BYTE(s, offset) ((s)->registers[(offset)])
#endif

#ifndef ASMC_TARGET
#define ASMC_TARGET asmc_target
#endif
void ASMC_TARGET(struct asmc_state *s);
uint64_t asmc_get_reg(const struct asmc_state *s, unsigned offset, unsigned bytes);
void asmc_set_reg(struct asmc_state *s, unsigned offset, unsigned bytes, uint64_t value);
uint64_t asmc_load(const struct asmc_state *s, uint64_t address, unsigned bytes);
void asmc_store(struct asmc_state *s, uint64_t address, unsigned bytes, uint64_t value);
#endif
