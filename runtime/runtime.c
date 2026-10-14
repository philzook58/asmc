#include "asmc_state.h"
#include <assert.h>

/* The lifter checks this when importing a runtime template. */
#ifdef ASMC_OBJECT_MEMORY
const unsigned asmc_memory_is_objects = 1;
#else
const unsigned asmc_memory_is_objects = 0;
#endif

/* ASMC replaces this body. Harnesses include only its declaration. */
void ASMC_TARGET(struct asmc_state *s) { (void)s; }

uint64_t asmc_get_reg(const struct asmc_state *s, unsigned offset, unsigned bytes) {
  assert(bytes >= 1 && bytes <= 8 && offset <= ASMC_REGISTER_BYTES - bytes);
  uint64_t result = 0;
  for (unsigned i = 0; i < bytes; ++i)
    result |= (uint64_t)s->registers[offset + i] << (8 * i);
  return result;
}
void asmc_set_reg(struct asmc_state *s, unsigned offset, unsigned bytes, uint64_t value) {
  assert(bytes >= 1 && bytes <= 8 && offset <= ASMC_REGISTER_BYTES - bytes);
  for (unsigned i = 0; i < bytes; ++i)
    s->registers[offset + i] = (uint8_t)(value >> (8 * i));
}
#ifndef ASMC_OBJECT_MEMORY
static uint64_t checked_offset(const struct asmc_state *s, uint64_t address, unsigned bytes) {
  assert(bytes >= 1 && bytes <= 8);
  assert(s->ram_size <= UINT64_MAX - s->ram_base);
  assert(address >= s->ram_base && address <= UINT64_MAX - (bytes - 1));
  uint64_t offset = address - s->ram_base;
  assert(s->ram_size >= bytes && offset <= s->ram_size - bytes);
  return offset;
}
#endif

uint64_t asmc_load(const struct asmc_state *s, uint64_t address, unsigned bytes) {
  uint64_t result = 0;
#ifdef ASMC_OBJECT_MEMORY
  (void)s;
  assert(bytes >= 1 && bytes <= 8);
  uint8_t *memory = (uint8_t *)(uintptr_t)address;
  assert(__CPROVER_r_ok(memory, bytes));
#else
  uint64_t offset = checked_offset(s, address, bytes);
  uint8_t *memory = s->ram + offset;
#endif
  for (unsigned i = 0; i < bytes; ++i)
    result |= (uint64_t)memory[i] << (8 * i);
  return result;
}
void asmc_store(struct asmc_state *s, uint64_t address, unsigned bytes, uint64_t value) {
#ifdef ASMC_OBJECT_MEMORY
  (void)s;
  assert(bytes >= 1 && bytes <= 8);
  uint8_t *memory = (uint8_t *)(uintptr_t)address;
  assert(__CPROVER_w_ok(memory, bytes));
#else
  uint64_t offset = checked_offset(s, address, bytes);
  uint8_t *memory = s->ram + offset;
#endif
  for (unsigned i = 0; i < bytes; ++i)
    memory[i] = (uint8_t)(value >> (8 * i));
}
