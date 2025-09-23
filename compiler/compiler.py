try:
    from bytecode import Instruction, Opcode  # type: ignore
    from ast_nodes import *  # type: ignore
except ModuleNotFoundError:
    from .bytecode import Instruction, Opcode  # type: ignore
    from .ast_nodes import *  # type: ignore


class ASTCompiler:
    """Translates assembly AST nodes into core VM bytecode using `Opcode`."""

    def __init__(self):
        self.instructions = []

    def emit(self, opcode, *args):
        self.instructions.append(Instruction(opcode, list(args)))

    def compile(self, nodes):
        for node in nodes:
            self.visit(node)
        self.emit(Opcode.HALT)
        return self.instructions

    def visit(self, node):
        if isinstance(node, MovNode):
            self.emit(Opcode.MOV, node.dst, node.src)
        elif isinstance(node, AddNode):
            self.emit(Opcode.ADD, node.dst, node.lhs, node.rhs)
        elif isinstance(node, SubNode):
            self.emit(Opcode.SUB, node.dst, node.lhs, node.rhs)
        elif isinstance(node, MulNode):
            self.emit(Opcode.MUL, node.dst, node.lhs, node.rhs)
        elif isinstance(node, DivNode):
            self.emit(Opcode.DIV, node.dst, node.lhs, node.rhs)
        elif isinstance(node, ModNode):
            self.emit(Opcode.MOD, node.dst, node.lhs, node.rhs)
        elif isinstance(node, NegNode):
            self.emit(Opcode.NEG, node.dst, node.src)

        elif isinstance(node, EqNode):
            self.emit(Opcode.EQ, node.dst, node.lhs, node.rhs)
        elif isinstance(node, GtNode):
            self.emit(Opcode.GT, node.dst, node.lhs, node.rhs)
        elif isinstance(node, LtNode):
            self.emit(Opcode.LT, node.dst, node.lhs, node.rhs)
        elif isinstance(node, AndNode):
            self.emit(Opcode.AND, node.dst, node.lhs, node.rhs)
        elif isinstance(node, OrNode):
            self.emit(Opcode.OR, node.dst, node.lhs, node.rhs)
        elif isinstance(node, NotNode):
            self.emit(Opcode.NOT, node.dst, node.src)
        elif isinstance(node, ClearNode):
            self.emit(Opcode.CLR, node.dst)
        elif isinstance(node, CmpImmNode):
            self.emit(Opcode.CMP_IMM, node.dst, node.src, node.imm)

        elif isinstance(node, AndBitNode):
            self.emit(Opcode.AND_BIT, node.dst, node.lhs, node.rhs)
        elif isinstance(node, OrBitNode):
            self.emit(Opcode.OR_BIT, node.dst, node.lhs, node.rhs)
        elif isinstance(node, XorNode):
            self.emit(Opcode.XOR, node.dst, node.lhs, node.rhs)
        elif isinstance(node, NotBitNode):
            self.emit(Opcode.NOT_BIT, node.dst, node.src)
        elif isinstance(node, ShlNode):
            self.emit(Opcode.SHL, node.dst, node.lhs, node.rhs)
        elif isinstance(node, ShrNode):
            self.emit(Opcode.SHR, node.dst, node.lhs, node.rhs)
        elif isinstance(node, SarNode):
            self.emit(Opcode.SAR, node.dst, node.lhs, node.rhs)

        elif isinstance(node, PrintNode):
            self.emit(Opcode.PRINT, node.var)
        elif isinstance(node, LabelNode):
            self.emit(Opcode.LABEL, node.name)
        elif isinstance(node, JumpNode):
            self.emit(Opcode.JMP, node.label)
        elif isinstance(node, JzNode):
            self.emit(Opcode.JZ, node.cond, node.label)
        elif isinstance(node, JnzNode):
            self.emit(Opcode.JNZ, node.cond, node.label)
        elif isinstance(node, JmpRelNode):
            self.emit(Opcode.JMP_REL, node.offset)

        elif isinstance(node, CallNode):
            self.emit(Opcode.CALL, node.name)
        elif isinstance(node, ReturnNode):
            self.emit(Opcode.RETURN, node.value)
        elif isinstance(node, ParamNode):
            self.emit(Opcode.PARAM, node.value)
        elif isinstance(node, ArgNode):
            self.emit(Opcode.ARG, node.dst)
        elif isinstance(node, ResultNode):
            self.emit(Opcode.RESULT, node.dst)

        elif isinstance(node, FuncNode):
            self.emit(Opcode.LABEL, node.name)
        elif isinstance(node, EndFuncNode):
            self.emit(Opcode.RETURN, "0")

        elif isinstance(node, IfNode):
            self.emit(Opcode.JZ, node.condition, node.else_label)
        elif isinstance(node, ElseNode):
            self.emit(Opcode.JMP, node.end_label)
            self.emit(Opcode.LABEL, node.end_label.replace("endif", "else"))  # 可省略
        elif isinstance(node, EndIfNode):
            pass  # 只是结构标记，不发射任何字节码

        elif isinstance(node, WhileNode):
            self.emit(Opcode.JZ, node.condition, node.end_label)
        elif isinstance(node, EndWhileNode):
            pass
        elif isinstance(node, BreakNode):
            self.emit(Opcode.JMP, node.end_label)

        elif isinstance(node, ArrInitNode):
            self.emit(Opcode.ARR_INIT, node.name, node.size)
        elif isinstance(node, ArrSetNode):
            self.emit(Opcode.ARR_SET, node.name, node.index, node.value)
        elif isinstance(node, ArrGetNode):
            self.emit(Opcode.ARR_GET, node.dst, node.name, node.index)
        elif isinstance(node, LenNode):
            self.emit(Opcode.LEN, node.dst, node.name)
        elif isinstance(node, PushNode):
            self.emit(Opcode.PUSH, node.src)
        elif isinstance(node, PopNode):
            self.emit(Opcode.POP, node.dst)
        elif isinstance(node, ArrCopyNode):
            self.emit(Opcode.ARR_COPY, node.dst, node.src, node.start, node.length)
        elif isinstance(node, IsObjNode):
            self.emit(Opcode.IS_OBJ, node.dst, node.src)
        elif isinstance(node, IsArrNode):
            self.emit(Opcode.IS_ARR, node.dst, node.src)
        elif isinstance(node, IsNullNode):
            self.emit(Opcode.IS_NULL, node.dst, node.src)
        elif isinstance(node, CoalesceNode):
            self.emit(Opcode.COALESCE, node.dst, node.lhs, node.rhs)

        elif isinstance(node, NoOpNode):
            pass
        else:
            raise NotImplementedError(f"Unsupported AST node: {type(node)}")
