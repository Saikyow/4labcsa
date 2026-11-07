# Синтаксический анализатор языка alg: рекурсивный спуск, токены -> AST.

from __future__ import annotations

from dataclasses import dataclass, field

from lexer import Token, tokenize


@dataclass(frozen=True)
class Number:
    value: int
    line: int


@dataclass(frozen=True)
class String:
    value: str
    line: int


@dataclass(frozen=True)
class Name:
    name: str
    line: int


@dataclass(frozen=True)
class Index:
    base: Expr
    index: Expr
    line: int


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[Expr, ...]
    line: int


@dataclass(frozen=True)
class Unary:
    op: str
    operand: Expr
    line: int


@dataclass(frozen=True)
class Binary:
    op: str
    left: Expr
    right: Expr
    line: int


Expr = Number | String | Name | Index | Call | Unary | Binary


@dataclass(frozen=True)
class Let:
    name: str
    size: int | None  # задан только для массива
    init: Expr | None  # у массива не бывает
    line: int


@dataclass(frozen=True)
class Assign:
    target: Name | Index
    value: Expr
    line: int


@dataclass(frozen=True)
class ExprStmt:
    expr: Expr
    line: int


@dataclass(frozen=True)
class If:
    cond: Expr
    then: Block
    otherwise: Block | None  # else if хранится как else с вложенным if
    line: int


@dataclass(frozen=True)
class While:
    cond: Expr
    body: Block
    line: int


@dataclass(frozen=True)
class Return:
    value: Expr | None
    line: int


@dataclass(frozen=True)
class Block:
    stmts: tuple[Stmt, ...]
    line: int


Stmt = Let | Assign | ExprStmt | If | While | Return | Block


@dataclass(frozen=True)
class Function:
    name: str
    params: tuple[str, ...]
    body: Block
    is_interrupt: bool
    line: int


@dataclass(frozen=True)
class Program:
    globals: tuple[Let, ...] = field(default_factory=tuple)
    functions: tuple[Function, ...] = field(default_factory=tuple)


# Парсер

BINARY_LEVELS: tuple[tuple[str, ...], ...] = (
    ("||",),
    ("&&",),
    ("|",),
    ("^",),
    ("&",),
    ("==", "!="),
    ("<", "<=", ">", ">="),
    ("<<", ">>"),
    ("+", "-"),
    ("*", "/", "%"),
)

UNARY_OPS = ("-", "!", "~")


class ParseError(Exception):
    def __init__(self, token: Token, message: str) -> None:
        super().__init__(f"line {token.line}: {message} (got {token.kind} {token.value!r})")


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def check(self, kind: str) -> bool:
        return self.current.kind == kind

    def check_op(self, ops: tuple[str, ...]) -> bool:
        return self.current.kind not in ("STRING", "IDENT", "NUMBER") and self.current.value in ops

    def advance(self) -> Token:
        token = self.current
        if token.kind != "EOF":
            self.pos += 1
        return token

    def expect(self, kind: str) -> Token:
        if not self.check(kind):
            raise ParseError(self.current, f"expected {kind}")
        return self.advance()

    def accept(self, kind: str) -> bool:
        if self.check(kind):
            self.advance()
            return True
        return False

    # Программа и функции
    def program(self) -> Program:
        global_vars: list[Let] = []
        functions: list[Function] = []
        while not self.check("EOF"):
            if self.check("LET"):
                global_vars.append(self.let())
            elif self.check("FN") or self.check("INTERRUPT"):
                functions.append(self.function())
            else:
                raise ParseError(self.current, "expected 'let', 'fn' or 'interrupt'")
        return Program(tuple(global_vars), tuple(functions))

    def function(self) -> Function:
        keyword = self.advance()
        name = self.expect("IDENT").value
        self.expect("LPAREN")
        params: list[str] = []
        if not self.check("RPAREN"):
            params.append(self.expect("IDENT").value)
            while self.accept("COMMA"):
                params.append(self.expect("IDENT").value)
        self.expect("RPAREN")
        is_interrupt = keyword.kind == "INTERRUPT"
        if is_interrupt and params:
            raise ParseError(keyword, "interrupt handler can't have parameters")
        return Function(name, tuple(params), self.block(), is_interrupt, keyword.line)

    # Операторы
    def block(self) -> Block:
        line = self.expect("LBRACE").line
        stmts: list[Stmt] = []
        while not self.check("RBRACE"):
            if self.check("EOF"):
                raise ParseError(self.current, "unclosed block")
            stmts.append(self.statement())
        self.advance()
        return Block(tuple(stmts), line)

    def statement(self) -> Stmt:
        kind = self.current.kind
        if kind == "LET":
            return self.let()
        if kind == "IF":
            return self.if_stmt()
        if kind == "WHILE":
            line = self.advance().line
            cond = self.paren_expr()
            return While(cond, self.block(), line)
        if kind == "RETURN":
            line = self.advance().line
            value = None if self.check("SEMICOLON") else self.expression()
            self.expect("SEMICOLON")
            return Return(value, line)
        if kind == "LBRACE":
            return self.block()
        return self.assign_or_expr()

    def let(self) -> Let:
        line = self.expect("LET").line
        name = self.expect("IDENT").value
        size: int | None = None
        init: Expr | None = None
        if self.accept("LBRACKET"):
            size = int(self.expect("NUMBER").value)
            self.expect("RBRACKET")
        elif self.accept("ASSIGN"):
            init = self.expression()
        self.expect("SEMICOLON")
        return Let(name, size, init, line)

    def if_stmt(self) -> If:
        line = self.expect("IF").line
        cond = self.paren_expr()
        then = self.block()
        otherwise: Block | None = None
        if self.accept("ELSE"):
            if self.check("IF"):
                nested = self.if_stmt()
                otherwise = Block((nested,), nested.line)
            else:
                otherwise = self.block()
        return If(cond, then, otherwise, line)

    def assign_or_expr(self) -> Stmt:
        line = self.current.line
        expr = self.expression()
        if self.accept("ASSIGN"):
            if not isinstance(expr, Name | Index):
                raise ParseError(self.current, "invalid assignment target")
            value = self.expression()
            self.expect("SEMICOLON")
            return Assign(expr, value, line)
        self.expect("SEMICOLON")
        return ExprStmt(expr, line)

    # Выражения
    def paren_expr(self) -> Expr:
        self.expect("LPAREN")
        expr = self.expression()
        self.expect("RPAREN")
        return expr

    def expression(self) -> Expr:
        return self.binary(0)

    def binary(self, level: int) -> Expr:
        if level == len(BINARY_LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.check_op(BINARY_LEVELS[level]):
            op = self.advance()
            right = self.binary(level + 1)
            left = Binary(op.value, left, right, op.line)
        return left

    def unary(self) -> Expr:
        if self.check_op(UNARY_OPS):
            op = self.advance()
            operand = self.unary()
            if op.value == "-" and isinstance(operand, Number):
                return Number(-operand.value, op.line)
            return Unary(op.value, operand, op.line)
        return self.postfix()

    def postfix(self) -> Expr:
        expr = self.primary()
        while self.check("LBRACKET"):
            line = self.advance().line
            index = self.expression()
            self.expect("RBRACKET")
            expr = Index(expr, index, line)
        return expr

    def primary(self) -> Expr:
        token = self.advance()
        if token.kind == "NUMBER":
            return Number(int(token.value), token.line)
        if token.kind == "STRING":
            return String(token.value, token.line)
        if token.kind == "LPAREN":
            expr = self.expression()
            self.expect("RPAREN")
            return expr
        if token.kind == "IDENT":
            if self.accept("LPAREN"):
                return Call(token.value, self.call_args(), token.line)
            return Name(token.value, token.line)
        raise ParseError(token, "expected expression")

    def call_args(self) -> tuple[Expr, ...]:
        args: list[Expr] = []
        if not self.check("RPAREN"):
            args.append(self.expression())
            while self.accept("COMMA"):
                args.append(self.expression())
        self.expect("RPAREN")
        return tuple(args)


def parse(source: str) -> Program:
    return Parser(tokenize(source)).program()


def dump_expr(expr: Expr) -> str:
    match expr:
        case Number(value):
            return str(value)
        case String(value):
            return repr(value)
        case Name(name):
            return name
        case Index(base, index):
            return f"([] {dump_expr(base)} {dump_expr(index)})"
        case Call(name, args):
            return f"(call {' '.join([name, *map(dump_expr, args)])})"
        case Unary(op, operand):
            return f"({op} {dump_expr(operand)})"
        case Binary(op, left, right):
            return f"({op} {dump_expr(left)} {dump_expr(right)})"


def dump_stmt(stmt: Stmt, indent: int) -> list[str]:
    pad = "  " * indent
    match stmt:
        case Let(name, size, init):
            suffix = f"[{size}]" if size is not None else ""
            value = f" = {dump_expr(init)}" if init is not None else ""
            return [f"{pad}let {name}{suffix}{value}"]
        case Assign(target, value):
            return [f"{pad}set {dump_expr(target)} = {dump_expr(value)}"]
        case ExprStmt(expr):
            return [f"{pad}expr {dump_expr(expr)}"]
        case Return(value):
            return [f"{pad}return" + (f" {dump_expr(value)}" if value is not None else "")]
        case While(cond, body):
            return [f"{pad}while {dump_expr(cond)}", *dump_block(body, indent + 1)]
        case If(cond, then, otherwise):
            lines = [f"{pad}if {dump_expr(cond)}", *dump_block(then, indent + 1)]
            if otherwise is not None:
                lines += [f"{pad}else", *dump_block(otherwise, indent + 1)]
            return lines
        case Block():
            return [f"{pad}block", *dump_block(stmt, indent + 1)]


def dump_block(block: Block, indent: int) -> list[str]:
    return [line for stmt in block.stmts for line in dump_stmt(stmt, indent)]


def dump(program: Program) -> str:
    lines: list[str] = []
    for var in program.globals:
        lines += dump_stmt(var, 0)
    for func in program.functions:
        keyword = "interrupt" if func.is_interrupt else "fn"
        lines.append(f"{keyword} {func.name}({', '.join(func.params)})")
        lines += dump_block(func.body, 1)
    return "\n".join(lines) + "\n"
