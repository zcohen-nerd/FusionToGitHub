"""The coverage gate's check that every test asserts something real."""

import os
import sys
import tempfile
import textwrap
import unittest

import _paths

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import coverage_gate  # noqa: E402

sys.path.remove(os.path.join(ROOT, "scripts"))


class AssertionLintTests(unittest.TestCase):
    def flagged(self, body):
        folder = tempfile.mkdtemp(prefix="ftg_lint_")
        self.addCleanup(_paths.force_rmtree, folder)
        source = "import unittest\nfrom unittest import mock\n\n\nclass T(unittest.TestCase):\n" + textwrap.indent(
            textwrap.dedent(body), "    "
        )
        with open(os.path.join(folder, "test_sample.py"), "w", encoding="utf-8") as fh:
            fh.write(source)
        return [p.split("::")[1].split(" ")[0] for p in coverage_gate.check_assertions(folder)]

    def test_tests_that_cannot_fail_are_flagged(self):
        flagged = self.flagged("""
            def test_constant(self):
                self.assertTrue(True)

            def test_constant_assert(self):
                assert 1

            def test_helper_that_is_not_an_assertion(self):
                failed_text("x")

            def test_mock_call_check_only(self):
                m = mock.Mock()
                m.assert_not_called()

            def test_only_inside_an_if(self):
                if False:
                    self.assertEqual(1, 2)
        """)
        self.assertEqual(sorted(flagged), sorted([
            "test_constant", "test_constant_assert", "test_helper_that_is_not_an_assertion",
            "test_mock_call_check_only", "test_only_inside_an_if",
        ]))

    def test_real_assertions_pass(self):
        self.assertEqual(self.flagged("""
            def test_equal(self):
                self.assertEqual(compute(), 2)

            def test_raises(self):
                with self.assertRaises(ValueError):
                    compute()

            def test_fail(self):
                self.fail("never") if broken() else None

            def test_statement(self):
                assert compute() == 2

            def test_helper(self):
                assert_pushed(self)
        """), [])


if __name__ == "__main__":
    unittest.main()
