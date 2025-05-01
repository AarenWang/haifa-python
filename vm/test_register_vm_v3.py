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
        
    def test_recursion_factorial(self):
        script = [
            "FUNC fact",
            "ARG n",
            "MOV one 1",
            "LT cond n one",
            "JZ cond recurse",
            "MOV ret 1",
            "RETURN ret",
            "LABEL recurse",
            "SUB n1 n one",
            "PARAM n1",
            "CALL fact",
            "RESULT res",
            "MUL ret res n",
            "RETURN ret",
            "ENDFUNC",
            "MOV x 5",
            "PARAM x",
            "CALL fact",
            "RESULT y",
            "PRINT y"
        ]
        interpreter = Interpreter(script)
        output = interpreter.run()
        print(f"Output: {output}")
        self.assertEqual(output, [120])
        
    def test_recursive_fibonacci(self):
        script = [
            "FUNC fib",
            "ARG n",
            "MOV two 2",
            "LT cond n two",
            "JZ cond recurse",
            "MOV ret n",
            "RETURN ret",
            "LABEL recurse",
            "MOV one 1",
            "SUB n1 n one",
            "SUB n2 n two",
            "PARAM n1",
            "CALL fib",
            "RESULT r1",
            "PARAM n2",
            "CALL fib",
            "RESULT r2",
            "ADD ret r1 r2",
            "RETURN ret",
            "ENDFUNC",
            "MOV x 7",
            "PARAM x",
            "CALL fib",
            "RESULT y",
            "PRINT y"
        ]
        interpreter = Interpreter(script)
        output = interpreter.run()
        print(f"Output: {output}")
        self.assertEqual(output, [13])  
            

if __name__ == '__main__':
    unittest.main()
