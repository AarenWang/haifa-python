try:
    from ast_nodes import *  # type: ignore
except ModuleNotFoundError:
    from .ast_nodes import *  # type: ignore
import itertools

def parse(script_lines):
    ast = []
    label_counter = itertools.count(0)
    label_map = {}
    stack = []

    def gen_label(prefix):
        return f"__{prefix}_{next(label_counter)}"

    for line in script_lines:
        parts = line.strip().split()
        if not parts:
            ast.append(NoOpNode())
            continue

        op = parts[0].upper()
        args = parts[1:]

        if op == "IF":
            else_label = gen_label("else")
            end_label = gen_label("endif")
            ast.append(IfNode(args[0], else_label))
            stack.append(("IF", else_label, end_label))
        elif op == "ELSE":
            if_top = stack[-1]
            if if_top[0] != "IF": raise SyntaxError("ELSE without IF")
            _, else_label, end_label = stack[-1]
            ast.append(ElseNode(end_label))
            ast.append(LabelNode(else_label))
        elif op == "ENDIF":
            if_top = stack.pop()
            if if_top[0] != "IF": raise SyntaxError("ENDIF without IF")
            _, else_label, end_label = if_top
            ast.append(LabelNode(end_label))
            ast.append(EndIfNode())

        elif op == "WHILE":
            start_label = gen_label("while_start")
            end_label = gen_label("while_end")
            ast.append(LabelNode(start_label))
            ast.append(WhileNode(args[0], end_label))
            stack.append(("WHILE", start_label, end_label))
        elif op == "ENDWHILE":
            while_top = stack.pop()
            if while_top[0] != "WHILE": raise SyntaxError("ENDWHILE without WHILE")
            start_label, end_label = while_top[1], while_top[2]
            ast.append(EndWhileNode())
            ast.append(JumpNode(start_label))
            ast.append(LabelNode(end_label))
        elif op == "BREAK":
            if not stack or stack[-1][0] != "WHILE": raise SyntaxError("BREAK outside WHILE")
            ast.append(BreakNode(stack[-1][2]))

        elif op == "MOV": ast.append(MovNode(*args))
        elif op == "ADD": ast.append(AddNode(*args))
        elif op == "SUB": ast.append(SubNode(*args))
        elif op == "MUL": ast.append(MulNode(*args))
        elif op == "DIV": ast.append(DivNode(*args))
        elif op == "MOD": ast.append(ModNode(*args))
        elif op == "NEG": ast.append(NegNode(*args))

        elif op == "EQ": ast.append(EqNode(*args))
        elif op == "GT": ast.append(GtNode(*args))
        elif op == "LT": ast.append(LtNode(*args))
        elif op == "AND": ast.append(AndNode(*args))
        elif op == "OR": ast.append(OrNode(*args))
        elif op == "NOT": ast.append(NotNode(*args))

        elif op == "AND_BIT": ast.append(AndBitNode(*args))
        elif op == "OR_BIT": ast.append(OrBitNode(*args))
        elif op == "XOR": ast.append(XorNode(*args))
        elif op == "NOT_BIT": ast.append(NotBitNode(*args))
        elif op == "SHL": ast.append(ShlNode(*args))
        elif op == "SHR": ast.append(ShrNode(*args))
        elif op == "SAR": ast.append(SarNode(*args))

        elif op == "PRINT": ast.append(PrintNode(*args))
        elif op == "LABEL": ast.append(LabelNode(*args))
        elif op == "JZ": ast.append(JzNode(*args))
        elif op == "JMP": ast.append(JumpNode(*args))

        elif op == "FUNC": ast.append(FuncNode(*args))
        elif op == "ENDFUNC": ast.append(EndFuncNode())
        elif op == "CALL": ast.append(CallNode(*args))
        elif op == "PARAM": ast.append(ParamNode(*args))
        elif op == "ARG": ast.append(ArgNode(*args))
        elif op == "RETURN": ast.append(ReturnNode(*args))
        elif op == "RESULT": ast.append(ResultNode(*args))

        elif op == "ARR_INIT": ast.append(ArrInitNode(*args))
        elif op == "ARR_SET": ast.append(ArrSetNode(*args))
        elif op == "ARR_GET": ast.append(ArrGetNode(*args))
        elif op == "LEN": ast.append(LenNode(*args))

        else:
            ast.append(NoOpNode())

    return ast
