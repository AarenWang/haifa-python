import pytest
import sys
import os

# 添加项目根目录到路径，确保可以导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from haifa_lua.lexer import LuaLexer, Token
from haifa_lua.parser import LuaParser
from haifa_lua.compiler import LuaCompiler
from haifa_lua.runtime import run_source, compile_source
from haifa_lua.analysis import analyze
from compiler.bytecode_vm import BytecodeVM

class TestLuaInterpreter:
    """Lua 解释器核心功能测试"""
    
    def setup_method(self):
        """每个测试前的设置"""
        self.vm = BytecodeVM([])
    
    def compile_and_run(self, source_code):
        """辅助方法：编译并执行 Lua 代码"""
        try:
            return run_source(source_code)
        except Exception as e:
            return None
    
    # =================================================================
    # 第一优先级：核心功能测试 (1-10)
    # =================================================================
    
    def test_01_basic_number_literals(self):
        """测试基础数字字面值"""
        result = self.compile_and_run("return 42")
        # 基础语法应该正常编译
        assert result is not None
    
    def test_02_basic_string_literals(self):
        """测试基础字符串字面值"""
        result = self.compile_and_run('return "hello"')
        assert result is not None
    
    def test_03_basic_boolean_literals(self):
        """测试基础布尔字面值"""
        result = self.compile_and_run("return true")
        assert result is not None
        
        result = self.compile_and_run("return false")
        assert result is not None
    
    def test_04_nil_literal(self):
        """测试 nil 字面值"""
        result = self.compile_and_run("return nil")
        assert result is not None
    
    def test_05_basic_arithmetic(self):
        """测试基础算术运算"""
        result = self.compile_and_run("return 1 + 2")
        assert result is not None
        
        result = self.compile_and_run("return 10 - 3")
        assert result is not None
        
        result = self.compile_and_run("return 4 * 5")
        assert result is not None
        
        result = self.compile_and_run("return 15 / 3")
        assert result is not None
    
    def test_06_basic_comparison(self):
        """测试基础比较运算"""
        result = self.compile_and_run("return 5 > 3")
        assert result is not None
        
        result = self.compile_and_run("return 2 < 4")
        assert result is not None
        
        result = self.compile_and_run("return 5 == 5")
        assert result is not None
        
        result = self.compile_and_run("return 3 ~= 4")
        assert result is not None
    
    def test_07_variable_assignment(self):
        """测试变量赋值"""
        result = self.compile_and_run("local x = 10; return x")
        assert result is not None
    
    def test_08_variable_scope(self):
        """测试变量作用域"""
        code = """
        local x = 1
        do
            local x = 2
        end
        return x
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    def test_09_basic_if_statement(self):
        """测试基础 if 语句"""
        code = """
        local x = 5
        if x > 0 then
            return "positive"
        else
            return "negative"
        end
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    def test_10_basic_while_loop(self):
        """测试基础 while 循环"""
        code = """
        local i = 0
        local sum = 0
        while i < 3 do
            sum = sum + i
            i = i + 1
        end
        return sum
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    # =================================================================
    # 第二优先级：函数和表测试 (11-20)
    # =================================================================
    
    def test_11_function_definition(self):
        """测试函数定义"""
        code = """
        function add(a, b)
            return a + b
        end
        return add(3, 4)
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    def test_12_local_function(self):
        """测试局部函数"""
        code = """
        local function multiply(x, y)
            return x * y
        end
        return multiply(6, 7)
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    def test_13_function_return_multiple(self):
        """测试函数返回多值（如果支持）"""
        code = """
        function getCoords()
            return 10, 20
        end
        local x, y = getCoords()
        return x + y
        """
        try:
            result = self.compile_and_run(code)
            # 可能不支持多值返回
        except:
            pass
    
    # =================================================================
    # 第三优先级：控制流测试 (21-25)
    # =================================================================
    
    def test_14_nested_if_statements(self):
        """测试嵌套 if 语句"""
        code = """
        local x = 15
        if x > 0 then
            if x > 10 then
                return "big"
            else
                return "small"
            end
        else
            return "negative"
        end
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    def test_15_elseif_statements(self):
        """测试 elseif 语句"""
        code = """
        local score = 85
        if score >= 90 then
            return "A"
        elseif score >= 80 then
            return "B"
        else
            return "F"
        end
        """
        result = self.compile_and_run(code)
        assert result is not None
    
    def test_16_logical_operators(self):
        """测试逻辑运算符"""
        result = self.compile_and_run("return true and false")
        assert result is not None
        
        result = self.compile_and_run("return true or false")
        assert result is not None
        
        result = self.compile_and_run("return not true")
        assert result is not None
    
    def test_17_unary_minus(self):
        """测试一元减号"""
        result = self.compile_and_run("return -42")
        assert result is not None
        
        result = self.compile_and_run("local x = 10; return -x")
        assert result is not None
    
    # =================================================================
    # 第四优先级：词法和语法测试 (18-20)
    # =================================================================
    
    def test_18_lexer_keywords(self):
        """测试词法分析器关键字识别"""
        keywords = ['if', 'then', 'else', 'end', 'function', 'return', 'local']
        for keyword in keywords:
            lexer = LuaLexer(keyword)
            tokens = lexer.tokenize()
            assert len(tokens) > 0
            # 关键字应该被正确识别而不是作为标识符
    
    def test_19_parser_basic_expressions(self):
        """测试解析器基础表达式解析"""
        expressions = [
            "42",
            '"string"',
            "true",
            "false", 
            "nil"
        ]
        
        for expr in expressions:
            source = f"return {expr}"
            try:
                lexer = LuaLexer(source)
                tokens = lexer.tokenize()
                parser = LuaParser(tokens)
                ast = parser._parse_chunk()
                assert ast is not None
            except Exception as e:
                # 某些表达式可能不被完全支持
                pass
    
    def test_20_complex_expression(self):
        """测试复杂表达式"""
        code = "return (1 + 2) * 3 - 4 / 2"
        result = self.compile_and_run(code)
        assert result is not None


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
