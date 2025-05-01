from graphviz import Digraph

class ASTVisualizer:
    def __init__(self):
        self.graph = Digraph(comment="AST")
        self.counter = 0

    def gen_id(self):
        self.counter += 1
        return f"node{self.counter}"

    def visualize(self, ast_nodes, output_file="ast", format="png"):
        prev_id = None
        for node in ast_nodes:
            label = type(node).__name__
            if hasattr(node, 'dst'):
                label += f"\\n{getattr(node, 'dst', '')}"
            if hasattr(node, 'name'):
                label += f"\\n{getattr(node, 'name', '')}"
            if hasattr(node, 'condition'):
                label += f"\\nif({getattr(node, 'condition')})"
            node_id = self.gen_id()
            self.graph.node(node_id, label=label, shape="box")
            if prev_id:
                self.graph.edge(prev_id, node_id)
            prev_id = node_id

        self.graph.render(filename=output_file, format=format, cleanup=True)
        print(f"AST graph written to {output_file}.{format}")