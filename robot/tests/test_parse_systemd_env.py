import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROBOT_ROOT = Path(__file__).resolve().parents[1]
PARSER = ROBOT_ROOT / "scripts" / "parse_systemd_env.py"


class ParseSystemdEnvironmentTest(unittest.TestCase):
    def run_parser(self, path: Path) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-B", str(PARSER), str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def decode_assignments(self, payload: bytes) -> list[str]:
        self.assertTrue(payload.endswith(b"\0"))
        return [part.decode("utf-8") for part in payload[:-1].split(b"\0")]

    def test_shell_syntax_is_emitted_literally_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "robot.env"
            path.write_text(
                "\n".join(
                    (
                        "# comment",
                        "PLAIN=value",
                        "DOLLAR=literal$missing_name",
                        "BACKTICK=`false`",
                        "SUBSHELL=$(false)",
                        'DOUBLE="quoted $HOME `false` $(false)"',
                        "SINGLE='quoted $HOME `false` $(false)'",
                        "EMPTY=",
                    )
                )
                + "\n",
                encoding="utf-8",
            )

            result = self.run_parser(path)

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(
            self.decode_assignments(result.stdout),
            [
                "PLAIN=value",
                "DOLLAR=literal$missing_name",
                "BACKTICK=`false`",
                "SUBSHELL=$(false)",
                "DOUBLE=quoted $HOME `false` $(false)",
                "SINGLE=quoted $HOME `false` $(false)",
                "EMPTY=",
            ],
        )

    def test_duplicate_keys_remain_ordered_for_last_assignment_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "robot.env"
            path.write_text("MODE=patrol\nMODE=mapping\n", encoding="utf-8")

            result = self.run_parser(path)

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(
            self.decode_assignments(result.stdout),
            ["MODE=patrol", "MODE=mapping"],
        )

    def test_invalid_variable_name_is_rejected_without_echoing_value(self) -> None:
        for assignment in (
            "BAD-NAME=do-not-print-this",
            "1BAD=do-not-print-this",
            "=do-not-print-this",
        ):
            with self.subTest(assignment=assignment.split("=", 1)[0]):
                with tempfile.TemporaryDirectory() as temporary:
                    path = Path(temporary) / "robot.env"
                    path.write_text(f"{assignment}\n", encoding="utf-8")

                    result = self.run_parser(path)

                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertNotIn(b"do-not-print-this", result.stderr)

    def test_nul_byte_is_rejected_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "robot.env"
            path.write_bytes(b"GOOD=value\nBROKEN=before\0after\n")

            result = self.run_parser(path)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_malformed_quote_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ros.env"
            path.write_text('MODE="mapping\n', encoding="utf-8")

            result = self.run_parser(path)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()
