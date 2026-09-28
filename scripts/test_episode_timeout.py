"""Check collector timeout boundaries without launching Isaac Sim.

Load the actual parser and Collector bodies through AST, as in the keyboard
event regression test. Simulator interactions are replaced with mocks.
"""
import argparse
import ast
import contextlib
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).with_name("collect_keyboard.py")
TREE = ast.parse(SOURCE.read_text())
start = next(i for i, n in enumerate(TREE.body)
             if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
             and n.targets[0].id == "ROOT")
end = next(i for i, n in enumerate(TREE.body)
           if isinstance(n, ast.If) and isinstance(n.test, ast.Attribute)
           and n.test.attr == "smoke_success_test")
PARSER = compile(ast.Module(body=TREE.body[start:end], type_ignores=[]), str(SOURCE), "exec")
CLASS = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "Collector")


def parse_args(args):
    namespace = {"__file__": str(SOURCE), "Path": Path, "argparse": argparse}
    with patch("sys.argv", [str(SOURCE), *args]):
        exec(PARSER, namespace)
    return namespace["a"]


class EpisodeTimeoutTests(unittest.TestCase):
    def collector(self, fps=50, seconds=60):
        namespace = {"a": SimpleNamespace(fps=fps, max_episode_seconds=seconds)}
        exec(compile(ast.Module(body=[CLASS], type_ignores=[]), str(SOURCE), "exec"), namespace)
        cls = namespace["Collector"]
        c = cls.__new__(cls)
        c.rec = SimpleNamespace(active=True, count=0, discard=Mock())
        c.reset = Mock()
        c.message = ""
        return c

    def test_task_defaults(self):
        expected = [60, 60, 120, 90, 60, 60, 120, 60, 120, 150]
        for i, seconds in enumerate(expected, 1):
            self.assertEqual(parse_args(["--task", f"T{i}"]).max_episode_seconds, seconds)

    def test_override_and_invalid_values(self):
        self.assertEqual(parse_args(["--task", "T10", "--max-episode-seconds", "90"]).max_episode_seconds, 90)
        for value in ["0", "-1", "nan", "inf", "1.5"]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                parse_args(["--max-episode-seconds", value])
            self.assertEqual(error.exception.code, 2)

    def test_exact_limit_discards_and_resets_at_all_frame_rates(self):
        for fps in [10, 20, 25, 50]:
            c = self.collector(fps=fps)
            c.rec.count = 60 * fps - 1
            self.assertFalse(c.finish_recording_step(False))
            c.rec.discard.assert_not_called()
            c.rec.count += 1
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(c.finish_recording_step(False))
            c.rec.discard.assert_called_once_with()
            c.reset.assert_called_once_with()
            self.assertIn("Time limit reached (60s)", c.message)

    def test_success_wins_at_limit_and_saves_early(self):
        for count in [2, 3000]:
            c = self.collector()
            c.rec.count = count
            c.command = Mock()
            self.assertTrue(c.finish_recording_step(True))
            c.command.assert_called_once_with("save")

    def test_idle_and_elapsed_wall_time_do_not_trigger_timeout(self):
        c = self.collector()
        c.time = 10000  # Scene clock includes time before recording.
        c.rec.count = 1
        self.assertFalse(c.finish_recording_step(False))
        c.rec.active = False
        c.rec.count = 3000
        self.assertFalse(c.finish_recording_step(False))
        c.rec.discard.assert_not_called()
        c.reset.assert_not_called()


if __name__ == "__main__":
    unittest.main()
