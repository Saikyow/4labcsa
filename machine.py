# Потактовая модель стекового процессора.
# Использование: python machine.py <target.bin> <input> [--no-cache]

from __future__ import annotations

import argparse
import ast
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cache import Access, Cache, DirectMemory, Memory, MemoryAccessError
from isa import (
    INTERRUPT_VECTOR,
    PORT_INPUT,
    PORT_OUTPUT,
    RESET_VECTOR,
    WORD_MASK,
    WORD_SIZE,
    Instruction,
    Opcode,
    bytes_to_words,
    decode,
    to_signed,
)

MEMORY_WORDS = 4096
DATA_STACK_SIZE = 32
RETURN_STACK_SIZE = 32
TICK_LIMIT = 10_000_000
LOG_LIMIT = 1000  # тактов в журнале

logger = logging.getLogger("machine")


class MachineError(Exception):
    pass


# Ввод-вывод


def parse_schedule(text: str) -> list[tuple[int, int]]:
    schedule = ast.literal_eval(text.strip() or "[]")
    if not isinstance(schedule, list):
        raise TypeError("expected a list of (tick, token) pairs")
    result: list[tuple[int, int]] = []
    for item in schedule:
        match item:
            case (int(tick), str(char)) if len(char) == 1:
                result.append((tick, ord(char)))
            case (int(tick), int(value)) if to_signed(value) == value:
                result.append((tick, value))
            case _:
                raise ValueError(f"bad item {item!r}")
    return sorted(result)


def show_token(value: int) -> str:
    return repr(chr(value)) if 0 <= value < 0x110000 else str(value)


class InputDevice:
    # Очереди нет: непрочитанный токен затирается следующим.

    def __init__(self, schedule: list[tuple[int, int]]) -> None:
        self.schedule = schedule
        self.next = 0
        self.value = 0
        self.irq = False

    def update(self, tick: int) -> list[str]:
        events: list[str] = []
        while self.next < len(self.schedule) and self.schedule[self.next][0] <= tick:
            value = self.schedule[self.next][1]
            if self.irq:
                events.append(f"input overrun: {show_token(self.value)} lost")
            self.value, self.irq = value, True
            self.next += 1
            events.append(f"input {show_token(value)} -> IRQ")
        return events

    def read(self) -> int:
        self.irq = False
        return self.value


class OutputDevice:
    def __init__(self) -> None:
        self.chars: list[str] = []

    def write(self, value: int) -> str:
        if not 0 <= value < 0x110000:
            raise MachineError(f"can't output {value}: not a character code")
        self.chars.append(chr(value))
        return f"out {show_token(value)}"


# DataPath


class PcSel(Enum):
    NEXT = "PC+4"
    IMM = "IR.operand"
    RS = "RS[RSP]"
    VECTOR = "int vector"


class ArSel(Enum):
    PC = "PC"
    TOS = "TOS"


class TosSel(Enum):
    ALU = "ALU"
    NOS = "NOS"
    IMM = "IR.operand"
    MEM = "MEM"
    PORT = "port"


class StackOp(Enum):
    PUSH = "push"
    POP = "pop"


class MemOp(Enum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class Signals:
    pc: PcSel | None = None
    ar: ArSel | None = None
    tos: TosSel | None = None
    ir: bool = False
    ds: StackOp | None = None
    rs: StackOp | None = None
    mem: MemOp | None = None
    port_out: bool = False
    ie: bool | None = None
    interrupt: bool | None = None
    halt: bool = False


def c_div(a: int, b: int) -> int:
    # Округление к нулю, а // в Python округляет вниз.
    quotient = abs(a) // abs(b)
    return quotient if (a < 0) == (b < 0) else -quotient


ALU_OPERATIONS: dict[Opcode, Callable[[int, int], int]] = {
    Opcode.ADD: lambda a, b: a + b,
    Opcode.SUB: lambda a, b: a - b,
    Opcode.MUL: lambda a, b: a * b,
    Opcode.DIV: c_div,
    Opcode.MOD: lambda a, b: a - c_div(a, b) * b,
    Opcode.AND: lambda a, b: a & b,
    Opcode.OR: lambda a, b: a | b,
    Opcode.XOR: lambda a, b: a ^ b,
    Opcode.SHL: lambda a, b: a << (b & 31),
    Opcode.SHR: lambda a, b: (a & WORD_MASK) >> (b & 31),
    Opcode.EQ: lambda a, b: int(a == b),
    Opcode.NE: lambda a, b: int(a != b),
    Opcode.LT: lambda a, b: int(a < b),
    Opcode.LE: lambda a, b: int(a <= b),
    Opcode.GT: lambda a, b: int(a > b),
    Opcode.GE: lambda a, b: int(a >= b),
    Opcode.NEG: lambda _, b: -b,
    Opcode.NOT: lambda _, b: ~b,
}


def alu(op: Opcode, left: int, right: int) -> int:
    if op in (Opcode.DIV, Opcode.MOD) and right == 0:
        raise MachineError("division by zero")
    return to_signed(ALU_OPERATIONS[op](left, right))


class DataPath:
    # TOS в регистре, остальной стек в DS, NOS = DS[SP-1].

    def __init__(self, memory: Cache | DirectMemory, input_device: InputDevice, output_device: OutputDevice) -> None:
        self.memory = memory
        self.input = input_device
        self.output = output_device
        self.pc = RESET_VECTOR
        self.ir = Instruction(Opcode.NOP)
        self.ar = 0
        # В памяти слова беззнаковые, знак появляется только в TOS.
        self.mdr = 0
        self.tos = 0
        self.ds = [0] * DATA_STACK_SIZE
        self.sp = 0
        self.rs = [0] * RETURN_STACK_SIZE
        self.rsp = 0
        self.ie = False
        self.in_interrupt = False

    @property
    def nos(self) -> int:
        if self.sp == 0:
            raise MachineError("data stack underflow")
        return self.ds[self.sp - 1]

    def memory_access(self, op: MemOp) -> Access:
        try:
            if op is MemOp.READ:
                access = self.memory.read(self.ar)
                self.mdr = access.value
                return access
            return self.memory.write(self.ar, self.tos & WORD_MASK)
        except MemoryAccessError as error:
            raise MachineError(str(error)) from error

    def pc_mux(self, sel: PcSel) -> int:
        match sel:
            case PcSel.NEXT:
                return self.pc + WORD_SIZE
            case PcSel.IMM:
                return self.ir.operand
            case PcSel.RS:
                if self.rsp == 0:
                    raise MachineError("return stack underflow")
                return self.rs[self.rsp - 1]
            case PcSel.VECTOR:
                return INTERRUPT_VECTOR

    def tos_mux(self, sel: TosSel) -> int:
        match sel:
            case TosSel.ALU:
                unary = self.ir.opcode in (Opcode.NEG, Opcode.NOT)
                return alu(self.ir.opcode, 0 if unary else self.nos, self.tos)
            case TosSel.NOS:
                return self.nos
            case TosSel.IMM:
                return self.ir.operand
            case TosSel.MEM:
                return to_signed(self.mdr)
            case TosSel.PORT:
                if self.ir.operand != PORT_INPUT:
                    raise MachineError(f"no input device on port {self.ir.operand}")
                return self.input.read()

    def data_stack(self, op: StackOp) -> None:
        match op:
            case StackOp.PUSH:
                if self.sp == DATA_STACK_SIZE:
                    raise MachineError("data stack overflow")
                self.ds[self.sp] = self.tos
                self.sp += 1
            case StackOp.POP:
                if self.sp == 0:
                    raise MachineError("data stack underflow")
                self.sp -= 1

    def return_stack(self, op: StackOp) -> None:
        if op is StackOp.PUSH:
            if self.rsp == RETURN_STACK_SIZE:
                raise MachineError("return stack overflow")
            self.rs[self.rsp] = self.pc
            self.rsp += 1
        else:
            self.rsp -= 1

    def apply(self, signals: Signals) -> list[str]:
        # Новые значения считаются из состояния до такта, регистры обновляются разом.
        new_tos = self.tos if signals.tos is None else self.tos_mux(signals.tos)
        new_pc = self.pc if signals.pc is None else self.pc_mux(signals.pc)
        events = self.ports(signals, new_tos)
        if signals.ar is not None:
            self.ar = self.pc if signals.ar is ArSel.PC else self.tos
        if signals.ir:
            try:
                self.ir = decode(self.mdr)
            except ValueError as error:
                raise MachineError(f"invalid instruction 0x{self.mdr:08X} at 0x{self.ar:04X}") from error
        if signals.ds is not None:
            self.data_stack(signals.ds)
        if signals.rs is not None:
            self.return_stack(signals.rs)
        if signals.ie is not None:
            self.ie = signals.ie
        if signals.interrupt is not None:
            self.in_interrupt = signals.interrupt
        self.tos, self.pc = new_tos, new_pc
        return events

    def ports(self, signals: Signals, new_tos: int) -> list[str]:
        if signals.tos is TosSel.PORT:
            return [f"in {show_token(new_tos)}"]
        if signals.port_out:
            if self.ir.operand != PORT_OUTPUT:
                raise MachineError(f"no output device on port {self.ir.operand}")
            return [self.output.write(self.tos)]
        return []


# ControlUnit


class Phase(Enum):
    FETCH = "fetch"
    READ = "read"
    EXECUTE = "exec"
    INTERRUPT = "irq"


FETCH_ADDRESS = Signals(ar=ArSel.PC)
FETCH_INSTRUCTION = Signals(mem=MemOp.READ, ir=True, pc=PcSel.NEXT)
ENTER_INTERRUPT = Signals(rs=StackOp.PUSH, pc=PcSel.VECTOR, ie=False, interrupt=True)
POP_TO_TOS = Signals(tos=TosSel.NOS, ds=StackOp.POP)

ONE_STEP = {
    Opcode.NOP: Signals(),
    Opcode.HALT: Signals(halt=True),
    Opcode.PUSH: Signals(tos=TosSel.IMM, ds=StackOp.PUSH),
    Opcode.DROP: POP_TO_TOS,
    Opcode.NEG: Signals(tos=TosSel.ALU),
    Opcode.NOT: Signals(tos=TosSel.ALU),
    Opcode.JMP: Signals(pc=PcSel.IMM),
    Opcode.CALL: Signals(pc=PcSel.IMM, rs=StackOp.PUSH),
    Opcode.RET: Signals(pc=PcSel.RS, rs=StackOp.POP),
    Opcode.IN: Signals(tos=TosSel.PORT, ds=StackOp.PUSH),
    Opcode.OUT: Signals(tos=TosSel.NOS, ds=StackOp.POP, port_out=True),
    Opcode.EI: Signals(ie=True),
    Opcode.DI: Signals(ie=False),
    Opcode.IRET: Signals(pc=PcSel.RS, rs=StackOp.POP, ie=True, interrupt=False),
}


def execute_steps(opcode: Opcode, zero: bool) -> tuple[Signals, ...]:
    if opcode in ONE_STEP:
        return (ONE_STEP[opcode],)
    match opcode:
        case Opcode.LOAD:
            return Signals(ar=ArSel.TOS), Signals(mem=MemOp.READ, tos=TosSel.MEM)
        case Opcode.STORE:
            return (
                Signals(ar=ArSel.TOS, tos=TosSel.NOS, ds=StackOp.POP),
                Signals(mem=MemOp.WRITE),
                POP_TO_TOS,
            )
        case Opcode.JZ:
            return (Signals(pc=PcSel.IMM if zero else None, tos=TosSel.NOS, ds=StackOp.POP),)
        case _:
            return (Signals(tos=TosSel.ALU, ds=StackOp.POP),)


class ControlUnit:
    # Пока память не ответила, CU остаётся на том же шаге.

    def __init__(self, datapath: DataPath, sources: dict[int, str]) -> None:
        self.dp = datapath
        self.sources = sources
        self.phase = Phase.FETCH
        self.step = 0
        self.wait = 0
        self.ticks = 0
        self.instructions = 0
        self.instr_address = RESET_VECTOR
        self.halted = False

    def signals(self) -> tuple[Signals, bool]:
        match self.phase:
            case Phase.FETCH:
                return FETCH_ADDRESS, True
            case Phase.READ:
                return FETCH_INSTRUCTION, True
            case Phase.INTERRUPT:
                return ENTER_INTERRUPT, True
            case Phase.EXECUTE:
                steps = execute_steps(self.dp.ir.opcode, self.dp.tos == 0)
                return steps[self.step], self.step == len(steps) - 1

    def tick(self) -> None:
        self.ticks += 1
        events = self.dp.input.update(self.ticks)
        signals, last = self.signals()
        if signals.mem is not None:
            if self.wait == 0:
                access = self.dp.memory_access(signals.mem)
                events.append(f"mem {signals.mem.value} 0x{self.dp.ar:04X}: {access.event}")
                self.wait = access.ticks
            self.wait -= 1
            if self.wait > 0:
                self.log([*events, f"wait memory ({self.wait} left)"])
                return
        events += self.dp.apply(signals)
        self.log(events)
        self.next_phase(signals, last)

    def next_phase(self, signals: Signals, last: bool) -> None:
        match self.phase:
            case Phase.FETCH:
                self.phase = Phase.READ
            case Phase.READ:
                self.phase, self.step = Phase.EXECUTE, 0
            case Phase.EXECUTE if not last:
                self.step += 1
            case Phase.EXECUTE | Phase.INTERRUPT:
                if self.phase is Phase.EXECUTE:
                    self.instructions += 1
                self.halted = signals.halt
                self.phase = Phase.INTERRUPT if self.dp.ie and self.dp.input.irq else Phase.FETCH
        if self.phase is Phase.FETCH:
            self.instr_address = self.dp.pc

    def log(self, events: list[str]) -> None:
        if not logger.isEnabledFor(logging.DEBUG):
            return
        dp = self.dp
        phase = f"exec {self.step + 1}" if self.phase is Phase.EXECUTE else self.phase.value
        nos = dp.ds[dp.sp - 1] if dp.sp else 0
        state = (
            f"PC: 0x{dp.pc:04X} AR: 0x{dp.ar:04X} IR: {dp.ir!s:<11} TOS: {dp.tos} NOS: {nos} "
            f"SP: {dp.sp} RSP: {dp.rsp} IE: {dp.ie:d} INT: {dp.in_interrupt:d}"
        )
        source = self.sources.get(self.instr_address, "")
        line = f"TICK: {self.ticks:>6} | 0x{self.instr_address:04X} {phase:<6} | {state}"
        if events:
            line += f" | {', '.join(events)}"
        logger.debug("%s", f"{line} ; {source}" if source else line)


# Запуск

LISTING_LINE = re.compile(r"^0x([0-9A-F]+) - [0-9A-F]{8} - .*? ; (.*)$")


def read_sources(listing: str) -> dict[int, str]:
    sources: dict[int, str] = {}
    for line in listing.splitlines():
        match = LISTING_LINE.match(line)
        if match:
            sources[int(match.group(1), 16)] = match.group(2)
    return sources


@dataclass(frozen=True)
class Result:
    output: str
    instructions: int
    ticks: int
    cache: str


def simulate(
    image: list[int],
    schedule: list[tuple[int, int]],
    sources: dict[int, str],
    *,
    use_cache: bool = True,
    log_limit: int = LOG_LIMIT,
) -> Result:
    try:
        memory = Memory(MEMORY_WORDS, image)
    except MemoryAccessError as error:
        raise MachineError(str(error)) from error
    memory_unit = Cache(memory) if use_cache else DirectMemory(memory)
    output = OutputDevice()
    cu = ControlUnit(DataPath(memory_unit, InputDevice(schedule), output), sources)
    level = logger.level
    while not cu.halted:
        if cu.ticks == TICK_LIMIT:
            logger.warning("tick limit %d reached", TICK_LIMIT)
            break
        if cu.ticks == log_limit:
            logger.debug("... log truncated after %d ticks", log_limit)
            logger.setLevel(logging.INFO)
        cu.tick()
    logger.setLevel(level)
    return Result("".join(output.chars), cu.instructions, cu.ticks, memory_unit.stats())


def main(target: str, input_file: str, *, use_cache: bool = True, log_limit: int = LOG_LIMIT) -> None:
    image = bytes_to_words(Path(target).read_bytes())
    try:
        schedule = parse_schedule(Path(input_file).read_text(encoding="utf-8"))
    except (ValueError, TypeError, SyntaxError) as error:
        raise SystemExit(f"bad input schedule: {error}") from error
    listing = Path(target + ".hex")
    sources = read_sources(listing.read_text(encoding="utf-8")) if listing.exists() else {}
    try:
        result = simulate(image, schedule, sources, use_cache=use_cache, log_limit=log_limit)
    except MachineError as error:
        raise SystemExit(f"machine error: {error}") from error
    print(result.output)
    print(f"instructions: {result.instructions} ticks: {result.ticks} {result.cache}")


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)-7s %(message)s")
    logger.setLevel(logging.DEBUG)
    args = argparse.ArgumentParser(description="stack processor simulator")
    args.add_argument("target")
    args.add_argument("input")
    args.add_argument("--no-cache", action="store_true", help="every memory access goes to memory")
    options = args.parse_args()
    main(options.target, options.input, use_cache=not options.no_cache)
