import unittest

from parser import parse
from compiler import ASTCompiler
from executor import Executor
from bytecode_vm import BytecodeVM


class TestJsonValueSupport(unittest.TestCase):
    def test_executor_handles_string_bool_null(self):
        script = [
            'MOV greeting "hello"',
            'PRINT greeting',
            'MOV flag true',
            'PRINT flag',
            'MOV nothing null',
            'PRINT nothing',
            'ARR_INIT arr 1',
            'ARR_SET arr 0 "world"',
            'ARR_GET fetched arr 0',
            'PRINT fetched',
        ]

        ast = parse(script)
        executor = Executor(ast)
        output = executor.run()

        self.assertEqual(output, ["hello", True, None, "world"])

    def test_bytecode_vm_handles_json_literals_and_arrays(self):
        script = [
            'MOV first "first"',
            'MOV second true',
            'PRINT first',
            'PRINT second',
        ]

        ast = parse(script)
        bytecode = ASTCompiler().compile(ast)
        vm = BytecodeVM(bytecode)
        output = vm.run()

        self.assertEqual(output, ["first", True])

    def test_executor_arrays_accept_direct_literals(self):
        script = [
            'ARR_INIT arr 2',
            'ARR_SET arr 0 "alpha"',
            'ARR_SET arr 1 "beta"',
            'ARR_GET first arr 0',
            'ARR_GET second arr 1',
            'PRINT first',
            'PRINT second',
        ]

        ast = parse(script)
        executor = Executor(ast)
        output = executor.run()

        self.assertEqual(output, ["alpha", "beta"])


if __name__ == '__main__':
    unittest.main()
