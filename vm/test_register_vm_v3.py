import unittest
from register_vm_v3 import Interpreter

class TestInterpreterVM(unittest.TestCase):
    def test_basic_arithmetic(self):
        script = [
            "MOV a 10",
            "MOV b 5",
            "ADD c a b",
            "MUL d a b",
            "PRINT c",
            "PRINT d"
        ]
        interpreter = Interpreter(script)
        output = interpreter.run()
        self.assertEqual(output, [15, 50])

    def test_missing_variable_defaults_to_zero(self):
        script = [
            "ADD a x y",  # x and y are not defined
            "PRINT a"
        ]
        interpreter = Interpreter(script)
        output = interpreter.run()
        self.assertEqual(output, [0])

    def test_multiple_mov_and_print(self):
        script = [
            "MOV x 3",
            "MOV y 4",
            "PRINT x",
            "PRINT y"
        ]
        interpreter = Interpreter(script)
        output = interpreter.run()
        self.assertEqual(output, [3, 4])

if __name__ == '__main__':
    unittest.main()
