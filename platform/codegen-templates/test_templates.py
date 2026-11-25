import glob
import os
import py_compile
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))


class TemplateSyntaxTests(unittest.TestCase):
    def test_every_python_template_compiles(self):
        files = [path for path in glob.glob(os.path.join(HERE, "*.py"))
                 if not os.path.basename(path).startswith(("test_", "cadquery_test_"))]
        self.assertGreaterEqual(len(files), 6)
        for path in files:
            with self.subTest(path=os.path.basename(path)):
                py_compile.compile(path, doraise=True)


if __name__ == "__main__":
    unittest.main()
