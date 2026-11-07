# Лексический анализатор языка alg.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int


KEYWORDS = {
    "let": "LET",
    "fn": "FN",
    "return": "RETURN",
    "if": "IF",
    "else": "ELSE",
    "while": "WHILE",
    "interrupt": "INTERRUPT",
}

SINGLE_CHAR = {
    "+": "PLUS",
    "-": "MINUS",
    "*": "STAR",
    "/": "SLASH",
    "%": "PERCENT",
    "=": "ASSIGN",
    "<": "LT",
    ">": "GT",
    "!": "NOT",
    "~": "TILDE",
    "&": "AMP",
    "|": "PIPE",
    "^": "CARET",
    "(": "LPAREN",
    ")": "RPAREN",
    "{": "LBRACE",
    "}": "RBRACE",
    "[": "LBRACKET",
    "]": "RBRACKET",
    ",": "COMMA",
    ";": "SEMICOLON",
}

DOUBLE_CHAR = {
    "==": "EQ",
    "!=": "NE",
    "<=": "LE",
    ">=": "GE",
    "&&": "AND",
    "||": "OR",
    "<<": "SHL",
    ">>": "SHR",
}

# токен 0 во вводе означает конец данных.
ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    '"': '"',
    "'": "'",
    "\\": "\\",
}


class LexerError(Exception):
    def __init__(self, line: int, message: str) -> None:
        super().__init__(f"line {line}: {message}")


def is_digit(char: str) -> bool:
    return "0" <= char <= "9"


def is_name_start(char: str) -> bool:
    return "a" <= char <= "z" or "A" <= char <= "Z" or char == "_"


def is_name_part(char: str) -> bool:
    return is_name_start(char) or is_digit(char)


class Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.line = 1
        self.tokens: list[Token] = []

    # За концом текста возвращаем "", чтобы вызывающему коду не проверять границы.
    def peek(self, offset: int = 0) -> str:
        index = self.pos + offset
        return self.source[index] if index < len(self.source) else ""

    def emit(self, kind: str, value: str) -> None:
        self.tokens.append(Token(kind, value, self.line))

    def read_while(self, predicate: Callable[[str], bool]) -> str:
        start = self.pos
        while self.peek() and predicate(self.peek()):
            self.pos += 1
        return self.source[start : self.pos]

    def read_quoted_char(self) -> str:
        char = self.peek()
        if char in ("", "\n"):
            raise LexerError(self.line, "unterminated literal")
        self.pos += 1
        if char != "\\":
            return char
        escape = self.peek()
        if escape not in ESCAPES:
            raise LexerError(self.line, f"unknown escape sequence \\{escape}")
        self.pos += 1
        return ESCAPES[escape]

    def read_string(self) -> None:
        self.pos += 1
        chars: list[str] = []
        while self.peek() != '"':
            chars.append(self.read_quoted_char())
        self.pos += 1
        self.emit("STRING", "".join(chars))

    def read_char(self) -> None:
        self.pos += 1
        char = self.read_quoted_char()
        if self.peek() != "'":
            raise LexerError(self.line, "char literal must contain exactly one symbol")
        self.pos += 1
        self.emit("NUMBER", str(ord(char)))

    def read_number(self) -> None:
        if self.source.startswith(("0x", "0X"), self.pos):
            self.pos += 2
            digits = self.read_while(lambda c: c in "0123456789abcdefABCDEF")
            if not digits:
                raise LexerError(self.line, "malformed hex literal")
            # Переводим в десятичную запись, чтобы парсер видел один формат чисел.
            self.emit("NUMBER", str(int(digits, 16)))
            return
        self.emit("NUMBER", self.read_while(is_digit))

    def skip_space_and_comments(self) -> bool:
        char = self.peek()
        if char == "\n":
            self.line += 1
            self.pos += 1
            return True
        if char in " \t\r":
            self.pos += 1
            return True
        if self.source.startswith("//", self.pos):
            self.read_while(lambda c: c != "\n")
            return True
        return False

    def read_operator(self) -> None:
        # Сначала двухсимвольные.
        pair = self.source[self.pos : self.pos + 2]
        if pair in DOUBLE_CHAR:
            self.emit(DOUBLE_CHAR[pair], pair)
            self.pos += 2
            return
        char = self.peek()
        if char in SINGLE_CHAR:
            self.emit(SINGLE_CHAR[char], char)
            self.pos += 1
            return
        raise LexerError(self.line, f"unexpected symbol {char!r}")

    def run(self) -> list[Token]:
        while self.pos < len(self.source):
            char = self.peek()
            if self.skip_space_and_comments():
                continue
            if is_digit(char):
                self.read_number()
            elif is_name_start(char):
                name = self.read_while(is_name_part)
                self.emit(KEYWORDS.get(name, "IDENT"), name)
            elif char == '"':
                self.read_string()
            elif char == "'":
                self.read_char()
            else:
                self.read_operator()
        self.emit("EOF", "")
        return self.tokens


def tokenize(source: str) -> list[Token]:
    return Lexer(source).run()
