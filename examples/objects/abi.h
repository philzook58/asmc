/* Private aliases let this harness exercise the three supported ABIs. */
#ifdef ASMC_RISCV_XLEN
#include "asmc_riscv.h"
#define enter_objects asmc_riscv_setup_objects_model
#define arg_ptr asmc_riscv_arg_ptr
#define arg_value asmc_riscv_arg
#define result_value asmc_riscv_result
#define result_ptr asmc_riscv_result_ptr
#define check_frame asmc_riscv_check
typedef struct asmc_riscv_frame frame_t;
#else
#include "asmc_x86.h"
#define enter_objects asmc_sysv_setup_objects_model
#define arg_ptr asmc_sysv_arg_ptr
#define arg_value asmc_sysv_arg64
#define result_value asmc_sysv_result64
#define result_ptr asmc_sysv_result_ptr
#define check_frame asmc_sysv_check
typedef struct asmc_sysv_frame frame_t;
#endif
