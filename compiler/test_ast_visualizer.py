import unittest
from unittest import mock

from .parser import parse
from . import ast_visualizer
from .ast_visualizer import ASTVisualizer


class DummyGraph:
    last_instance = None

    def __init__(self, comment="AST"):
        self.comment = comment
        self.nodes = []
        self.edges = []
        self.render_calls = []
        DummyGraph.last_instance = self

    def node(self, node_id, label=None, shape=None):
        self.nodes.append((node_id, label, shape))

    def edge(self, from_id, to_id):
        self.edges.append((from_id, to_id))

    def render(self, filename=None, format=None, cleanup=False):
        self.render_calls.append((filename, format, cleanup))
        return filename


class TestASTVisualizer(unittest.TestCase):
    def setUp(self):
        script = [
            "MOV a 5",
            "MOV b 10",
            "ADD c a b",
            "IF c",
            "MOV d 1",
            "ELSE",
            "MOV d 0",
            "ENDIF",
            "PRINT d",
        ]
        self.ast_nodes = parse(script)

    def test_visualize_uses_graph_api(self):
        viz = ASTVisualizer(graph_class=DummyGraph)
        viz.visualize(self.ast_nodes, output_file="ast_graph", format="png")

        graph = DummyGraph.last_instance
        self.assertIsNotNone(graph)
        self.assertEqual(len(graph.nodes), len(self.ast_nodes))
        self.assertEqual(len(graph.edges), len(self.ast_nodes) - 1)
        self.assertEqual(graph.render_calls, [("ast_graph", "png", True)])

    def test_missing_graphviz_raises(self):
        with mock.patch.object(ast_visualizer, "Digraph", None):
            with self.assertRaisesRegex(RuntimeError, "Graphviz package"):
                ASTVisualizer()


if __name__ == "__main__":
    unittest.main()
