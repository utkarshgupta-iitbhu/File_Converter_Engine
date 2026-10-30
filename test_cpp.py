"""Manual smoke test for the optional C++ byte-inversion extension."""
from pathlib import Path
from tempfile import TemporaryDirectory

import cpp_engine

with TemporaryDirectory(prefix="fce_cpp_test_") as temp_dir:
    source = Path(temp_dir) / "input.bin"
    output = Path(temp_dir) / "output.bin"
    original = b"File Converter Engine: C++ smoke test\x00\xff"
    source.write_bytes(original)
    cpp_engine.invert_file_bytes(str(source), str(output))
    expected = bytes((~value) & 0xFF for value in original)
    assert output.read_bytes() == expected, "C++ byte inversion output did not match expected bytes"
    print("C++ extension smoke test passed.")
