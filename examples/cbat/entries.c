#include "asmc_state.h"

/* Both binary functions get their own GOTO body, with one common runtime. */
void original(struct asmc_state *s) { (void)s; }
void patched(struct asmc_state *s) { (void)s; }
