# Память и кеш: set-associative, LRU, write-back + write-allocate.
# Промах +MEMORY_LATENCY, грязная вытесняемая строка ещё +MEMORY_LATENCY.

from __future__ import annotations

from dataclasses import dataclass, field

from isa import WORD_SIZE

MEMORY_LATENCY = 10
HIT_LATENCY = 1


class MemoryAccessError(Exception):
    pass


class Memory:
    def __init__(self, size_words: int, image: list[int]) -> None:
        if len(image) > size_words:
            raise MemoryAccessError(f"program ({len(image)} words) doesn't fit in memory ({size_words} words)")
        self.words = image + [0] * (size_words - len(image))

    def index(self, address: int) -> int:
        if address % WORD_SIZE:
            raise MemoryAccessError(f"unaligned access to 0x{address:04X}")
        if not 0 <= address < len(self.words) * WORD_SIZE:
            raise MemoryAccessError(f"access out of memory: 0x{address:04X}")
        return address // WORD_SIZE


@dataclass(frozen=True)
class Access:
    value: int
    ticks: int
    event: str


class DirectMemory:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def read(self, address: int) -> Access:
        return Access(self.memory.words[self.memory.index(address)], MEMORY_LATENCY, "memory")

    def write(self, address: int, value: int) -> Access:
        self.memory.words[self.memory.index(address)] = value
        return Access(value, MEMORY_LATENCY, "memory")

    def stats(self) -> str:
        return "cache: off"


@dataclass
class Line:
    tag: int = 0
    valid: bool = False
    dirty: bool = False
    last_used: int = 0  # для LRU
    words: list[int] = field(default_factory=list)


class Cache:
    def __init__(self, memory: Memory, sets: int = 16, ways: int = 2, line_words: int = 4) -> None:
        self.memory = memory
        self.sets = sets
        self.line_words = line_words
        self.lines = [[Line(words=[0] * line_words) for _ in range(ways)] for _ in range(sets)]
        self.clock = 0
        self.hits = 0
        self.misses = 0

    # Адрес слова: | tag | set | word in line |
    def split(self, address: int) -> tuple[int, int, int]:
        word = self.memory.index(address)
        line_number, offset = divmod(word, self.line_words)
        tag, set_index = divmod(line_number, self.sets)
        return tag, set_index, offset

    def line_address(self, tag: int, set_index: int) -> int:
        return (tag * self.sets + set_index) * self.line_words * WORD_SIZE

    def lookup(self, address: int) -> tuple[Line, int, int, str]:
        tag, set_index, offset = self.split(address)
        self.clock += 1
        ways = self.lines[set_index]
        for way, line in enumerate(ways):
            if line.valid and line.tag == tag:
                self.hits += 1
                line.last_used = self.clock
                return line, offset, HIT_LATENCY, f"hit set {set_index} way {way}"

        self.misses += 1
        way, victim = min(enumerate(ways), key=lambda item: (item[1].valid, item[1].last_used))
        ticks = HIT_LATENCY + MEMORY_LATENCY
        event = f"miss set {set_index} way {way}"
        if victim.valid and victim.dirty:
            start = self.memory.index(self.line_address(victim.tag, set_index))
            self.memory.words[start : start + self.line_words] = victim.words
            ticks += MEMORY_LATENCY
            event += f", write back 0x{self.line_address(victim.tag, set_index):04X}"
        start = self.memory.index(self.line_address(tag, set_index))
        ways[way] = Line(tag, True, False, self.clock, self.memory.words[start : start + self.line_words])
        return ways[way], offset, ticks, f"{event}, fill 0x{self.line_address(tag, set_index):04X}"

    def read(self, address: int) -> Access:
        line, offset, ticks, event = self.lookup(address)
        return Access(line.words[offset], ticks, event)

    def write(self, address: int, value: int) -> Access:
        line, offset, ticks, event = self.lookup(address)
        line.words[offset] = value
        line.dirty = True
        return Access(value, ticks, event)

    def stats(self) -> str:
        return f"cache: hits {self.hits} misses {self.misses}"
