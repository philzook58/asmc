/* Optional source instrumentation for this example, not ASMC call tracing. */
#ifdef ASMC_RECORD_CALLS
#define RECORD_CALL(data, bit) (*(data) |= (bit))
#else
#define RECORD_CALL(data, bit) ((void)0)
#endif
