# Транслятор alg -> машинный код.
# Использование: python translator.py <source.alg> <target.bin> [<target.ast>]

from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

from isa import (
    IMM_MAX,
    IMM_MIN,
    RESET_VECTOR,
    WORD_MASK,
    WORD_SIZE,
    Instruction,
    Opcode,
    words_to_bytes,
)
from lexer import LexerError
from parser import (
    Assign,
    Binary,
    Block,
    Call,
    Expr,
    ExprStmt,
    Function,
    If,
    Index,
    Let,
    Name,
    Number,
    ParseError,
    Program,
    Return,
    Stmt,
    String,
    Unary,
    While,
    dump,
    parse,
)

BINARY_OPCODES = {
    "+": Opcode.ADD,
    "-": Opcode.SUB,
    "*": Opcode.MUL,
    "/": Opcode.DIV,
    "%": Opcode.MOD,
    "&": Opcode.AND,
    "|": Opcode.OR,
    "^": Opcode.XOR,
    "<<": Opcode.SHL,
    ">>": Opcode.SHR,
    "==": Opcode.EQ,
    "!=": Opcode.NE,
    "<": Opcode.LT,
    "<=": Opcode.LE,
    ">": Opcode.GT,
    ">=": Opcode.GE,
}


# имя -> (число аргументов, оставляет ли значение на стеке)
BUILTINS = {
    "in": (1, True),
    "out": (2, False),
    "ei": (0, False),
    "di": (0, False),
}

ENTRY_POINT = "main"
# Точка в начале, чтобы не совпасть с именами из программы.
START_LABEL = ".start"


class TranslationError(Exception):
    def __init__(self, line: int | None, message: str) -> None:
        super().__init__(message if line is None else f"line {line}: {message}")


@dataclass(frozen=True)
class Op:
    opcode: Opcode
    operand: int | str = 0
    line: int = 0  # 0 у служебного кода
    note: str = ""  # подпись служебного кода в листинге


@dataclass(frozen=True)
class Label:
    name: str


@dataclass(frozen=True)
class DataItem:
    label: str
    words: tuple[int | str, ...]
    comment: str


@dataclass(frozen=True)
class Symbol:
    label: str
    # Массив в выражении даёт адрес, скаляр даёт значение.
    is_array: bool


@dataclass
class Scope:
    function: Function | None
    symbols: dict[str, Symbol] = field(default_factory=dict)


def called_functions(node: object) -> set[str]:
    if isinstance(node, tuple):
        return set().union(*map(called_functions, node))
    if not is_dataclass(node):
        return set()
    names = {node.name} if isinstance(node, Call) and node.name not in BUILTINS else set()
    return names.union(*(called_functions(getattr(node, f.name)) for f in fields(node)))


def reachable(graph: dict[str, set[str]], root: str) -> set[str]:
    seen: set[str] = set()
    stack = [root]
    while stack:
        name = stack.pop()
        if name not in seen:
            seen.add(name)
            stack.extend(graph.get(name, set()))
    return seen


def check_call_graph(program: Program) -> None:
    # Локальные переменные статические, поэтому запрещены рекурсия и общие с обработчиком функции.
    functions = {func.name: func for func in program.functions}
    graph = {func.name: called_functions(func.body) for func in program.functions}
    for func in program.functions:
        for callee in graph[func.name]:
            if callee not in functions:
                raise TranslationError(func.line, f"call of undefined function '{callee}'")
            if functions[callee].is_interrupt:
                raise TranslationError(func.line, f"interrupt handler '{callee}' can't be called")
        if any(func.name in reachable(graph, callee) for callee in graph[func.name]):
            raise TranslationError(func.line, f"recursion is not supported: '{func.name}'")
    handlers = [func for func in program.functions if func.is_interrupt]
    if len(handlers) > 1:
        raise TranslationError(handlers[1].line, "only one interrupt handler is allowed")
    if handlers and ENTRY_POINT in functions:
        shared = reachable(graph, ENTRY_POINT) & reachable(graph, handlers[0].name)
        if shared:
            raise TranslationError(
                handlers[0].line,
                f"functions shared with interrupt handler: {sorted(shared)}",
            )


class CodeGen:
    def __init__(self, program: Program) -> None:
        self.program = program
        self.functions = {func.name: func for func in program.functions}
        self.code: list[Op | Label] = []
        self.data: list[DataItem] = []
        self.literals: dict[int, str] = {}
        self.label_counter = 0
        self.line = 0
        self.globals = Scope(None)
        self.scope = self.globals

    def new_label(self, hint: str) -> str:
        self.label_counter += 1
        return f".{hint}{self.label_counter}"

    def emit(self, opcode: Opcode, operand: int | str = 0, note: str = "") -> None:
        self.code.append(Op(opcode, operand, 0 if note else self.line, note))

    def mark(self, label: str) -> None:
        self.code.append(Label(label))

    def literal(self, value: int) -> str:
        # Числа вне imm24 хранятся в пуле литералов.
        if value not in self.literals:
            label = f".lit{len(self.literals)}"
            self.literals[value] = label
            self.data.append(DataItem(label, (value & WORD_MASK,), f"literal {value}"))
        return self.literals[value]

    # Строки не дедуплицируем: они изменяемые.
    def string(self, value: str) -> str:
        label = f".str{sum(item.label.startswith('.str') for item in self.data)}"
        words = (len(value), *(ord(char) for char in value))
        self.data.append(DataItem(label, words, f"pstr {value!r}"))
        return label

    def declare(self, var: Let, init_word: int | str = 0) -> None:
        if var.name in self.scope.symbols:
            raise TranslationError(var.line, f"redeclaration of '{var.name}'")
        prefix = f"{self.scope.function.name}." if self.scope.function else ""
        label = prefix + var.name
        if var.size is not None:
            if var.size <= 0:
                raise TranslationError(var.line, f"invalid array size {var.size}")
            self.data.append(DataItem(label, (0,) * var.size, f"array [{var.size}]"))
        else:
            self.data.append(DataItem(label, (init_word,), "var"))
        self.scope.symbols[var.name] = Symbol(label, var.size is not None)

    def lookup(self, name: str, line: int) -> Symbol:
        for scope in (self.scope, self.globals):
            if name in scope.symbols:
                return scope.symbols[name]
        raise TranslationError(line, f"undefined variable '{name}'")

    def generate(self) -> None:
        # 0x00: jmp .start, 0x04: вектор прерывания, дальше код, после него данные.
        for var in self.program.globals:
            self.declare_global(var)
        handler = next((func for func in self.program.functions if func.is_interrupt), None)
        if ENTRY_POINT not in self.functions:
            raise TranslationError(None, f"function '{ENTRY_POINT}' is not defined")

        self.emit(Opcode.JMP, START_LABEL, note="reset vector")
        if handler is None:
            self.emit(Opcode.IRET, note="interrupt vector (no handler)")
        else:
            self.emit(Opcode.JMP, handler.name, note="interrupt vector")
        self.mark(START_LABEL)
        if handler is not None:
            self.emit(Opcode.EI, note="start: enable interrupts")
        self.emit(Opcode.CALL, ENTRY_POINT, note="start")
        self.emit(Opcode.HALT, note="start")
        for func in self.program.functions:
            self.function(func)

    def declare_global(self, var: Let) -> None:
        self.line = var.line
        # У переменных и функций общие метки.
        if var.name in self.functions:
            raise TranslationError(var.line, f"'{var.name}' is already a function name")
        # Значение кладётся прямо в образ памяти, поэтому только константа.
        match var.init:
            case None:
                self.declare(var)
            case Number(value):
                self.declare(var, value & WORD_MASK)
            case String(value):
                self.declare(var, self.string(value))
            case _:
                raise TranslationError(var.line, "global initializer must be a constant")

    def function(self, func: Function) -> None:
        self.scope = Scope(func)
        self.line = func.line
        self.mark(func.name)
        # Последний аргумент на вершине стека.
        for param in reversed(func.params):
            self.declare(Let(param, None, None, func.line))
            self.emit(Opcode.PUSH, self.scope.symbols[param].label)
            self.emit(Opcode.STORE)
        self.block(func.body)
        if func.is_interrupt:
            self.emit(Opcode.IRET, note=f"end of {func.name}")
        else:
            self.emit(Opcode.PUSH, 0, note=f"end of {func.name}: implicit return 0")
            self.emit(Opcode.RET, note=f"end of {func.name}")
        self.scope = self.globals

    def block(self, block: Block) -> None:
        for stmt in block.stmts:
            self.statement(stmt)

    def statement(self, stmt: Stmt) -> None:
        self.line = stmt.line
        match stmt:
            case Let():
                self.declare(stmt)
                # Массив не обнуляется: сохраняется между вызовами.
                if stmt.size is None:
                    self.store(Name(stmt.name, stmt.line), stmt.init or Number(0, stmt.line))
            case Assign(target, value):
                self.store(target, value)
            case ExprStmt(Call(name, args)) if name in BUILTINS and not BUILTINS[name][1]:
                self.builtin(name, args, stmt.line)
            case ExprStmt(expr):
                self.expr(expr)
                self.emit(Opcode.DROP)
            case If():
                self.if_stmt(stmt)
            case While(cond, body):
                start, end = self.new_label("while"), self.new_label("endwhile")
                self.mark(start)
                self.expr(cond)
                self.emit(Opcode.JZ, end)
                self.block(body)
                self.emit(Opcode.JMP, start)
                self.mark(end)
            case Return(value):
                self.return_stmt(value, stmt.line)
            case Block():
                self.block(stmt)

    def store(self, target: Name | Index, value: Expr) -> None:
        # store: адрес на вершине, значение под ним.
        self.expr(value)
        if isinstance(target, Index):
            self.element_address(target)
        else:
            symbol = self.lookup(target.name, target.line)
            if symbol.is_array:
                raise TranslationError(target.line, f"can't assign to array '{target.name}'")
            self.emit(Opcode.PUSH, symbol.label)
        self.emit(Opcode.STORE)

    def if_stmt(self, stmt: If) -> None:
        else_label, end_label = self.new_label("else"), self.new_label("endif")
        self.expr(stmt.cond)
        self.emit(Opcode.JZ, else_label if stmt.otherwise else end_label)
        self.block(stmt.then)
        if stmt.otherwise:
            self.emit(Opcode.JMP, end_label)
            self.mark(else_label)
            self.block(stmt.otherwise)
        self.mark(end_label)

    def return_stmt(self, value: Expr | None, line: int) -> None:
        func = self.scope.function
        if func is None:
            raise TranslationError(line, "return outside of function")
        if func.is_interrupt:
            if value is not None:
                raise TranslationError(line, "interrupt handler can't return a value")
            self.emit(Opcode.IRET)
            return
        self.expr(value if value is not None else Number(0, line))
        self.emit(Opcode.RET)

    # Инвариант: код выражения оставляет на стеке ровно одно значение.
    def expr(self, expr: Expr) -> None:
        match expr:
            case Number(value):
                self.number(value)
            case String(value):
                self.emit(Opcode.PUSH, self.string(value))
            case Name(name):
                symbol = self.lookup(name, expr.line)
                self.emit(Opcode.PUSH, symbol.label)
                if not symbol.is_array:
                    self.emit(Opcode.LOAD)
            case Index():
                self.element_address(expr)
                self.emit(Opcode.LOAD)
            case Call(name, args):
                self.call(name, args, expr.line)
            case Unary(op, operand):
                self.unary(op, operand)
            case Binary("&&" | "||"):
                self.logical(expr)
            case Binary(op, left, right):
                self.expr(left)
                self.expr(right)
                self.emit(BINARY_OPCODES[op])

    def number(self, value: int) -> None:
        if IMM_MIN <= value <= IMM_MAX:
            self.emit(Opcode.PUSH, value)
        else:
            self.emit(Opcode.PUSH, self.literal(value))
            self.emit(Opcode.LOAD)

    def element_address(self, expr: Index) -> None:
        self.expr(expr.base)
        self.expr(expr.index)
        self.emit(Opcode.PUSH, 2)
        self.emit(Opcode.SHL)
        self.emit(Opcode.ADD)

    def unary(self, op: str, operand: Expr) -> None:
        self.expr(operand)
        if op == "-":
            self.emit(Opcode.NEG)
        elif op == "~":
            self.emit(Opcode.NOT)
        else:
            self.emit(Opcode.PUSH, 0)
            self.emit(Opcode.EQ)

    def logical(self, expr: Binary) -> None:
        # Результат нормализуем к 0/1, иначе 2 && 3 дало бы 3.
        short, end = self.new_label("short"), self.new_label("endlogic")
        self.expr(expr.left)
        if expr.op == "&&":
            self.emit(Opcode.JZ, short)
            self.expr(expr.right)
            self.emit(Opcode.JZ, short)
            self.emit(Opcode.PUSH, 1)
            self.emit(Opcode.JMP, end)
            self.mark(short)
            self.emit(Opcode.PUSH, 0)
        else:
            self.emit(Opcode.JZ, short)
            self.emit(Opcode.PUSH, 1)
            self.emit(Opcode.JMP, end)
            self.mark(short)
            self.expr(expr.right)
            self.emit(Opcode.PUSH, 0)
            self.emit(Opcode.NE)
        self.mark(end)

    def call(self, name: str, args: tuple[Expr, ...], line: int) -> None:
        if name in BUILTINS:
            if not BUILTINS[name][1]:
                raise TranslationError(line, f"'{name}' doesn't return a value")
            self.builtin(name, args, line)
            return
        func = self.functions.get(name)
        if func is None:
            raise TranslationError(line, f"undefined function '{name}'")
        if len(args) != len(func.params):
            raise TranslationError(line, f"'{name}' expects {len(func.params)} arguments, got {len(args)}")
        for arg in args:
            self.expr(arg)
        self.emit(Opcode.CALL, name)

    def builtin(self, name: str, args: tuple[Expr, ...], line: int) -> None:
        if len(args) != BUILTINS[name][0]:
            raise TranslationError(line, f"'{name}' expects {BUILTINS[name][0]} arguments")
        if name in ("in", "out"):
            port = args[0]
            # Порт зашит в инструкцию, поэтому только константа.
            if not isinstance(port, Number):
                raise TranslationError(line, "port number must be a constant")
            if name == "out":
                self.expr(args[1])
            self.emit(Opcode.IN if name == "in" else Opcode.OUT, port.value)
            return
        self.emit(Opcode.EI if name == "ei" else Opcode.DI)


@dataclass(frozen=True)
class MemoryWord:
    address: int
    word: int
    text: str
    line: int = 0
    note: str = ""


def link(codegen: CodeGen) -> list[MemoryWord]:
    # Два прохода: адреса меток, затем кодирование.
    addresses: dict[str, int] = {}
    address = RESET_VECTOR
    for item in codegen.code:
        if isinstance(item, Label):
            addresses[item.name] = address
        else:
            address += WORD_SIZE
    for data in codegen.data:
        addresses[data.label] = address
        address += WORD_SIZE * len(data.words)

    def resolve(value: int | str) -> int:
        return addresses[value] if isinstance(value, str) else value

    image: list[MemoryWord] = []
    for item in codegen.code:
        if isinstance(item, Op):
            instr = Instruction(item.opcode, resolve(item.operand))
            text = str(instr)
            if isinstance(item.operand, str):
                text = f"{item.opcode.name.lower()} 0x{instr.operand:04X} ({item.operand})"
            image.append(MemoryWord(len(image) * WORD_SIZE, instr.encode(), text, item.line, item.note))
    for data in codegen.data:
        for offset, value in enumerate(data.words):
            comment = f"{data.label}: {data.comment}" if offset == 0 else f"{data.label}+{offset}"
            image.append(MemoryWord(len(image) * WORD_SIZE, resolve(value), "data", note=comment))
    return image


def translate(source: str) -> tuple[Program, list[MemoryWord]]:
    program = parse(source)
    check_call_graph(program)
    codegen = CodeGen(program)
    codegen.generate()
    return program, link(codegen)


def listing(image: list[MemoryWord], source: str) -> str:
    lines = source.splitlines()
    result: list[str] = []
    for word in image:
        text = f"0x{word.address:04X} - {word.word:08X} - {word.text}"
        if word.note:
            text = f"{text:<48} ; {word.note}"
        elif word.line:
            text = f"{text:<48} ; {word.line}: {lines[word.line - 1].strip()}"
        result.append(text)
    return "\n".join(result) + "\n"


def main(source_path: str, target_path: str, ast_path: str | None = None) -> None:
    source = Path(source_path).read_text(encoding="utf-8")
    program, image = translate(source)
    Path(target_path).write_bytes(words_to_bytes([word.word for word in image]))
    Path(target_path + ".hex").write_text(listing(image, source), encoding="utf-8")
    if ast_path is not None:
        Path(ast_path).write_text(dump(program), encoding="utf-8")
    code_words = sum(1 for word in image if word.text != "data")
    print(f"source LoC: {len(source.splitlines())} code instr: {code_words} data words: {len(image) - code_words}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        raise SystemExit("Usage: python translator.py <source.alg> <target.bin> [<target.ast>]")
    try:
        main(*sys.argv[1:])
    except (LexerError, ParseError, TranslationError) as error:
        raise SystemExit(f"translation error: {error}") from error
