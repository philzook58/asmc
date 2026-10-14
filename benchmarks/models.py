"""Small scalar workloads; each family varies one explicit parameter."""
from dataclasses import dataclass

KINDS = {"linear": 1, "memory-read": 2, "memory-write": 3, "branches": 4,
         "multiply": 5, "objects": 6, "dead-work": 7, "calls": 1, "call-bound": 1}
SIZES = {"linear": (4, 16, 64), "memory-read": (64, 256, 1024),
         "memory-write": (64, 256, 1024), "branches": (2, 4, 8),
         "multiply": (8, 16, 32), "objects": (1, 4, 16),
         "dead-work": (4, 16, 64), "calls": (1, 2, 4), "call-bound": (1, 2, 4)}


@dataclass(frozen=True)
class Case:
    family: str
    size: int
    memory: str = "ram"
    dispatch: bool = False
    fixed_index: bool = False
    bad: bool = False
    short_bound: bool = False
    bad_pointer: bool = False

    @property
    def name(self):
        parts = [self.family, str(self.size), self.memory]
        if self.dispatch: parts.append("dispatch")
        if self.fixed_index: parts.append("fixed")
        if self.bad: parts.append("bad")
        if self.short_bound: parts.append("short")
        if self.bad_pointer: parts.append("invalid-pointer")
        return "-".join(parts)

    @property
    def work(self):
        return 2 if self.family == "call-bound" else self.size

    @property
    def bound(self):
        if self.short_bound: return 1
        if self.family in ("calls", "call-bound"):
            return (2 * self.work + 2) * (self.size if self.family == "call-bound" else 1)
        if self.dispatch: return 2 * self.size + 2
        return None

    def assembly(self):
        body = ["mov %rdi,%rax"]
        if self.family in ("calls", "call-bound"):
            body = ["sub $8,%rsp", "mov %rdi,%rax"] + ["call helper"] * self.work + ["add $8,%rsp"]
        elif self.family == "linear":
            body += ["add $1,%rax"] * self.size
        elif self.family == "dead-work":
            body += ["imul %rsi,%rcx", "add %rcx,%rdx"] * self.size
        elif self.family == "memory-read":
            body = ["mov (%rdi,%rsi),%rax"]
        elif self.family == "memory-write":
            body = ["mov %rdx,(%rdi,%rsi)", "mov (%rdi,%rsi),%rax"]
        elif self.family == "branches":
            for i in range(self.size):
                body += [f"test ${1 << i},%rsi", f"jz skip_{i}", "add $1,%rax", f"skip_{i}:"]
        elif self.family == "multiply":
            body += ["add %rsi,%rax", "imul %rax,%rax"]
        elif self.family == "objects":
            body = ["mov (%rdi),%rax"]
        lines = [".text", ".globl target", ".type target,@function", "target:", *body,
                 "ret", ".size target,.-target"]
        if self.family in ("calls", "call-bound"):
            lines += [".globl helper", ".type helper,@function", "helper:", "add $1,%rax", "ret",
                      ".size helper,.-helper"]
        lines += ['.section .note.GNU-stack,"",@progbits', ""]
        return "\n".join(lines)

    def defines(self):
        ram_size = self.size + 128 if self.family.startswith("memory-") and self.memory == "ram" else 128
        flags = [f"-DBENCH_KIND={KINDS[self.family]}", f"-DBENCH_SIZE={self.work}", f"-DBENCH_RAM={ram_size}"]
        if self.memory == "objects": flags += ["-DASMC_OBJECT_MEMORY"]
        if self.fixed_index: flags += ["-DBENCH_FIXED_INDEX"]
        if self.bad: flags += ["-DBENCH_BAD"]
        if self.bad_pointer: flags += ["-DBENCH_BAD_POINTER"]
        return flags

    def objects_header(self):
        lines = [f"uint64_t object_{i};" for i in range(self.size)]
        lines += ["unsigned which;", f"__CPROVER_assume(which < {self.size});", "uint64_t *selected = &object_0;"]
        lines += [f"if (which == {i}) selected = &object_{i};" for i in range(1, self.size)]
        return "\n".join(lines) + "\n"


def cases(families, sizes=None, smoke=False):
    result = [Case("linear", 1), Case("linear", 1, bad=True), Case("calls", 1, short_bound=True),
              Case("objects", 1, "objects", bad_pointer=True)]
    if smoke:
        return result + [Case("memory-write", 64, "objects"), Case("branches", 2, dispatch=True)]
    for family in families:
        for size in sizes or SIZES[family]:
            if family in ("memory-read", "memory-write"):
                for memory in ("ram", "objects"):
                    result += [Case(family, size, memory), Case(family, size, memory, fixed_index=True)]
            elif family == "branches":
                result += [Case(family, size), Case(family, size, dispatch=True)]
            else:
                result.append(Case(family, size, "objects" if family == "objects" else "ram"))
    return list(dict.fromkeys(result))
