# Система команд. Инструкция занимает одно слово: [opcode:8][operand:24], big-endian.

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

WORD_SIZE = 4
WORD_MASK = 0xFFFF_FFFF
OPERAND_BITS = 24
OPERAND_MASK = (1 << OPERAND_BITS) - 1
IMM_MIN = -(1 << (OPERAND_BITS - 1))
IMM_MAX = (1 << (OPERAND_BITS - 1)) - 1

RESET_VECTOR = 0x00
INTERRUPT_VECTOR = 0x04

PORT_INPUT = 0
PORT_OUTPUT = 1


class Opcode(IntEnum):
    NOP = 0x00
    HALT = 0x01
    # работа со стеком
    PUSH = 0x10
    DROP = 0x12
    # память
    LOAD = 0x20
    STORE = 0x21
    # арифметика и логика
    ADD = 0x30
    SUB = 0x31
    MUL = 0x32
    DIV = 0x33
    MOD = 0x34
    AND = 0x35
    OR = 0x36
    XOR = 0x37
    SHL = 0x38
    SHR = 0x39
    EQ = 0x3A
    NE = 0x3B
    LT = 0x3C
    LE = 0x3D
    GT = 0x3E
    GE = 0x3F
    # унарные
    NEG = 0x40
    NOT = 0x41
    # управление
    JMP = 0x50
    JZ = 0x51
    CALL = 0x52
    RET = 0x53
    # ввод-вывод и прерывания
    IN = 0x60
    OUT = 0x61
    EI = 0x70
    DI = 0x71
    IRET = 0x72


WITH_OPERAND = frozenset({Opcode.PUSH, Opcode.JMP, Opcode.JZ, Opcode.CALL, Opcode.IN, Opcode.OUT})


# Урезаем до 32 бит.
def to_signed(value: int) -> int:
    value &= WORD_MASK
    return value - (1 << 32) if value & 0x8000_0000 else value


@dataclass(frozen=True)
class Instruction:
    opcode: Opcode
    operand: int = 0

    def encode(self) -> int:
        low, high = (IMM_MIN, IMM_MAX) if self.opcode == Opcode.PUSH else (0, OPERAND_MASK)
        if not low <= self.operand <= high:
            raise ValueError(
                f"operand {self.operand} of '{self.opcode.name.lower()}' doesn't fit in {OPERAND_BITS} bits"
            )
        return (self.opcode << OPERAND_BITS) | (self.operand & OPERAND_MASK)

    def __str__(self) -> str:
        name = self.opcode.name.lower()
        if self.opcode in (Opcode.JMP, Opcode.JZ, Opcode.CALL):
            return f"{name} 0x{self.operand:04X}"
        if self.opcode in WITH_OPERAND:
            return f"{name} {self.operand}"
        return name


def decode(word: int) -> Instruction:
    opcode = Opcode(word >> OPERAND_BITS)
    operand = word & OPERAND_MASK
    if opcode == Opcode.PUSH and operand & (1 << (OPERAND_BITS - 1)):
        operand -= 1 << OPERAND_BITS
    return Instruction(opcode, operand)


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join((word & WORD_MASK).to_bytes(WORD_SIZE, "big") for word in words)


def bytes_to_words(data: bytes) -> list[int]:
    return [int.from_bytes(data[i : i + WORD_SIZE], "big") for i in range(0, len(data), WORD_SIZE)]
