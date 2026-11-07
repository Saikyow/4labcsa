# Golden-тесты: исходник -> транслятор -> машина. Обновить эталоны: make update-golden

from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path
from typing import Any

import pytest

import machine
import translator
from isa import bytes_to_words

LOG_LIMIT = 300
EXAMPLES = Path(__file__).parent / "examples"


def hex_dump(data: bytes) -> str:
    words = [data[i : i + 4].hex().upper() for i in range(0, len(data), 4)]
    return "\n".join(" ".join(words[i : i + 8]) for i in range(0, len(words), 8)) + "\n"


@pytest.mark.golden_test("golden/*.yml")
def test_translator_and_machine(golden: Any, caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    source, schedule = golden["in_source"], golden["in_stdin"]
    # in_source должен совпадать с файлом из examples/.
    assert any(source == path.read_text(encoding="utf-8") for path in EXAMPLES.glob("*.alg"))

    source_file, input_file = tmp_path / "source.alg", tmp_path / "input.txt"
    target, ast = tmp_path / "target.bin", tmp_path / "target.ast"
    source_file.write_text(source, encoding="utf-8")
    input_file.write_text(schedule, encoding="utf-8")

    caplog.set_level(logging.DEBUG, logger=machine.logger.name)
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        translator.main(str(source_file), str(target), str(ast))
        print("=" * 5)
        machine.main(str(target), str(input_file), log_limit=LOG_LIMIT)
    log = caplog.text

    no_cache = machine.simulate(
        bytes_to_words(target.read_bytes()),
        machine.parse_schedule(schedule),
        {},
        use_cache=False,
        log_limit=0,
    )

    assert ast.read_text(encoding="utf-8") == golden.out["out_ast"]
    assert hex_dump(target.read_bytes()) == golden.out["out_code"]
    assert Path(f"{target}.hex").read_text(encoding="utf-8") == golden.out["out_code_hex"]
    assert stdout.getvalue() == golden.out["out_stdout"]
    no_cache_stdout = f"{no_cache.output}\ninstructions: {no_cache.instructions} ticks: {no_cache.ticks}\n"
    assert no_cache_stdout == golden.out["out_no_cache"]
    assert log == golden.out["out_log"]
