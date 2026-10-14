#ifndef ASMC_STATE_H
#define ASMC_STATE_H
#include <stdint.h>

#define ASMC_REGISTER_BYTES 0x300

struct asmc_state {
  uint8_t registers[ASMC_REGISTER_BYTES];
  uint8_t *ram;
  uint64_t ram_base;
  uint64_t ram_size;
  uint64_t return_address;
};

#ifndef ASMC_TARGET
#define ASMC_TARGET asmc_target
#endif
void ASMC_TARGET(struct asmc_state *s);
uint64_t asmc_get_reg(const struct asmc_state *s, unsigned offset, unsigned bytes);
void asmc_set_reg(struct asmc_state *s, unsigned offset, unsigned bytes, uint64_t value);
uint64_t asmc_load(const struct asmc_state *s, uint64_t address, unsigned bytes);
void asmc_store(struct asmc_state *s, uint64_t address, unsigned bytes, uint64_t value);
#endif
