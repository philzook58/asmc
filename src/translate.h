#pragma once
#include "lifter.h"
#include <goto-programs/goto_model.h>
void translate(goto_modelt &model, const Instructions &instructions, const std::string &listing,
               const ElfImage &image, const std::string &target, bool dispatch_branches = false,
               bool object_memory = false);
