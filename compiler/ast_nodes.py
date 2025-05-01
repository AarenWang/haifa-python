from abc import ABC, abstractmethod

class ASTNode(ABC):
    @abstractmethod
    def execute(self, context):
        pass


# 基础运算
class MovNode(ASTNode):
    def __init__(self, dst, src): self.dst = dst; self.src = src
    def execute(self, context): context.registers[self.dst] = context.val(self.src)

class AddNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) + context.val(self.rhs)

class SubNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) - context.val(self.rhs)

class MulNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) * context.val(self.rhs)

class DivNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) // context.val(self.rhs)

class ModNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) % context.val(self.rhs)

class NegNode(ASTNode):
    def __init__(self, dst, src): self.dst = dst; self.src = src
    def execute(self, context): context.registers[self.dst] = -context.val(self.src)


# 比较与逻辑运算
class EqNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = int(context.val(self.lhs) == context.val(self.rhs))

class GtNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = int(context.val(self.lhs) > context.val(self.rhs))

class LtNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = int(context.val(self.lhs) < context.val(self.rhs))

class AndNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = int(bool(context.val(self.lhs)) and bool(context.val(self.rhs)))

class OrNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = int(bool(context.val(self.lhs)) or bool(context.val(self.rhs)))

class NotNode(ASTNode):
    def __init__(self, dst, src): self.dst = dst; self.src = src
    def execute(self, context): context.registers[self.dst] = int(not bool(context.val(self.src)))


# 位操作 AST 节点
class AndBitNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) & context.val(self.rhs)

class OrBitNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) | context.val(self.rhs)

class XorNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) ^ context.val(self.rhs)

class NotBitNode(ASTNode):
    def __init__(self, dst, src): self.dst = dst; self.src = src
    def execute(self, context): context.registers[self.dst] = ~context.val(self.src)

class ShlNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) << context.val(self.rhs)

class ShrNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = (context.val(self.lhs) % (1 << 32)) >> context.val(self.rhs)

class SarNode(ASTNode):
    def __init__(self, dst, lhs, rhs): self.dst = dst; self.lhs = lhs; self.rhs = rhs
    def execute(self, context): context.registers[self.dst] = context.val(self.lhs) >> context.val(self.rhs)


# 控制结构节点（IF/WHILE）
class IfNode(ASTNode):
    def __init__(self, condition, else_label): self.condition = condition; self.else_label = else_label
    def execute(self, context):
        if context.val(self.condition) == 0: context.pc = context.labels[self.else_label] - 1

class ElseNode(ASTNode):
    def __init__(self, end_label): self.end_label = end_label
    def execute(self, context): context.pc = context.labels[self.end_label] - 1

class EndIfNode(ASTNode):
    def execute(self, context): pass

class WhileNode(ASTNode):
    def __init__(self, condition, end_label): self.condition = condition; self.end_label = end_label
    def execute(self, context):
        if not context.val(self.condition): context.pc = context.labels[self.end_label] - 1
        else: context.loop_stack.append(context.pc)

class EndWhileNode(ASTNode):
    def execute(self, context):
        if context.loop_stack: context.pc = context.loop_stack.pop() - 1

class BreakNode(ASTNode):
    def __init__(self, end_label): self.end_label = end_label
    def execute(self, context): context.pc = context.labels[self.end_label] - 1


# 流程控制
class JumpNode(ASTNode):
    def __init__(self, label): self.label = label
    def execute(self, context): context.pc = context.labels[self.label] - 1

class JzNode(ASTNode):
    def __init__(self, cond, label): self.cond = cond; self.label = label
    def execute(self, context):
        if context.val(self.cond) == 0: context.pc = context.labels[self.label] - 1

class LabelNode(ASTNode):
    def __init__(self, name): self.name = name
    def execute(self, context): pass


# 函数调用相关
class FuncNode(ASTNode):
    def __init__(self, name): self.name = name
    def execute(self, context): pass

class EndFuncNode(ASTNode):
    def execute(self, context):
        if context.call_stack: context.pc, context.param_stack = context.call_stack.pop(); context.pc -= 1

class CallNode(ASTNode):
    def __init__(self, name): self.name = name
    def execute(self, context):
        context.call_stack.append((context.pc + 1, list(context.param_stack)))
        context.param_stack.clear()
        context.pc = context.labels[self.name] - 1

class ParamNode(ASTNode):
    def __init__(self, value): self.value = value
    def execute(self, context): context.param_stack.append(context.val(self.value))

class ArgNode(ASTNode):
    def __init__(self, dst): self.dst = dst
    def execute(self, context):
        if context.param_stack: context.registers[self.dst] = context.param_stack.pop(0)

class ReturnNode(ASTNode):
    def __init__(self, value): self.value = value
    def execute(self, context):
        context.return_value = context.val(self.value)
        if context.call_stack: context.pc, context.param_stack = context.call_stack.pop(); context.pc -= 1

class ResultNode(ASTNode):
    def __init__(self, dst): self.dst = dst
    def execute(self, context): context.registers[self.dst] = context.return_value


# 数组
class ArrInitNode(ASTNode):
    def __init__(self, name, size): self.name = name; self.size = int(size)
    def execute(self, context): context.arrays[self.name] = [0] * self.size

class ArrSetNode(ASTNode):
    def __init__(self, name, index, value): self.name = name; self.index = index; self.value = value
    def execute(self, context): context.arrays[self.name][context.val(self.index)] = context.val(self.value)

class ArrGetNode(ASTNode):
    def __init__(self, dst, name, index): self.dst = dst; self.name = name; self.index = index
    def execute(self, context): context.registers[self.dst] = context.arrays[self.name][context.val(self.index)]

class LenNode(ASTNode):
    def __init__(self, dst, name): self.dst = dst; self.name = name
    def execute(self, context): context.registers[self.dst] = len(context.arrays[self.name])


# 输出与空操作
class PrintNode(ASTNode):
    def __init__(self, var): self.var = var
    def execute(self, context): context.output.append(context.val(self.var))

class NoOpNode(ASTNode):
    def execute(self, context): pass
