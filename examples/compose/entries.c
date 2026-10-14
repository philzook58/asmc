#include "asmc_state.h"

/* Empty bodies give goto-cc the types; ASMC replaces each by its chosen name. */
void lifted_add_one(struct asmc_state *s) { (void)s; }
void lifted_sum(struct asmc_state *s) { (void)s; }
