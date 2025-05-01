from ast_nodes import *

class ExecutionContext:
    def __init__(self):
        self.registers = {}
        self.arrays = {}
        self.labels = {}
        self.call_stack = []
        self.param_stack = []
        self.loop_stack = []
        self.return_value = None
        self.output = []
        self.pc = 0

    def val(self, x):
        return int(x) if x.lstrip("-").isdigit() else self.registers.get(x, 0)


class Executor:
    def __init__(self, ast_nodes):
        self.nodes = ast_nodes
        self.context = ExecutionContext()
        self.index_labels()

    def index_labels(self):
        for i, node in enumerate(self.nodes):
            if isinstance(node, LabelNode):
                self.context.labels[node.name] = i
            elif isinstance(node, FuncNode):
                self.context.labels[node.name] = i + 1

    def run(self):
        ctx = self.context
        while ctx.pc < len(self.nodes):
            node = self.nodes[ctx.pc]
            node.execute(ctx)
            ctx.pc += 1
        return ctx.output
