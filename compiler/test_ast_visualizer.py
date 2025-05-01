from parser import parse
from ast_visualizer import ASTVisualizer

script = [
    "MOV a 5",
    "MOV b 10",
    "ADD c a b",
    "IF c",
    "MOV d 1",
    "ELSE",
    "MOV d 0",
    "ENDIF",
    "PRINT d"
]

ast = parse(script)
viz = ASTVisualizer()
viz.visualize(ast, output_file="ast_graph", format="png")
