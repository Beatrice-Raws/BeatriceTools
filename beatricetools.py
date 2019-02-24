import ast
from   typing import Any, List

import vapoursynth as vs
from   vapoursynth import core


class ExprStr(ast.NodeVisitor):
    """
    Drop-in wrapper for Expr() string in infix form.

    Usage:

    ``core.std.Expr([clip1, clip2], ExprStr('x * 0.5 + y * 0.5'))``

    All operators and functions of Expr are supported, but input string must contain a valid Python expression, therefore syntax slightly differs:
    1. Parentheses ``()`` are supported
    2. Equality operator is ``==``
    3. Python conditional expression ``b if a else c`` is used for conditional operator
    
    It should be noted that though chaining of comparison operators is syntactically correct, it's semantics completely differs for Python and Expr interpreter.

    More examples:

    ``>>> print(ExprStr('swap(sqrt(a) * (0 if b < 100 else c), e)'))``

    ``a sqrt b 100 < 0 c ? * e swap``

    ``>>> print(ExprStr('a > b < c >= d'))``

    ``a b > c < d >=``
    """

    import re
    variables = 'abcdefghijklmnopqrstuvwxyz'

    operators = {
        ast.Add:  '+',
        ast.Sub:  '-',
        ast.Mult: '*',
        ast.Div:  '/',

        ast.Eq:   '=',
        ast.Gt:   '>',
        ast.Lt:   '<',
        ast.GtE: '>=',
        ast.LtE: '<='
    }

    functions = {
        'abs' : 1,
        'exp' : 1,
        'log' : 1,
        'not' : 1,
        'sqrt': 1,

        'and' : 2,
        'max' : 2,
        'min' : 2,
        'or'  : 2,
        'pow' : 2,
        'xor' : 2,
    }

    functions_re = {
        re.compile(r'dup\d*') : 1,
        re.compile(r'swap\d*'): 2
    }

    def __init__(self, input_string: str):
        self.stack: List[str] = []
        self.visit(ast.parse(input_string, mode='eval'))

    def visit_Num(self, node: ast.Num) -> None:
        self.stack.append(str(node.n))

    def visit_Name(self, node: ast.Name) -> None:
        if (len(node.id) > 1
            or node.id not in self.variables):
            raise SyntaxError(f'ExprStr: clip name \'{node.id}\' is not valid.')

        self.stack.append(node.id)

    def visit_Compare(self, node: ast.Compare) -> Any:
        for i in range(len(node.ops) - 1, -1, -1):
            if type(node.ops[i]) not in self.operators:
                raise SyntaxError(f'ExprStr: operator \'{type(node.ops[i])}\' is not supported.')

            self.stack.append(self.operators[type(node.ops[i])])

            self.visit(node.comparators[i])
            
        self.visit(node.left)

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if type(node.op) not in self.operators:
            raise SyntaxError(f'ExprStr: operator \'{type(node.op)}\' is not supported.')

        self.stack.append(self.operators[type(node.op)])

        self.visit(node.right)
        self.visit(node.left)

    def visit_Call(self, node: ast.Call) -> Any:
        import re

        is_re_function = False
        args_required  = 0
        if node.func.id not in self.functions:
            for pattern, args_count in self.functions_re.items():
                if pattern.fullmatch(node.func.id):
                    is_re_function = True
                    args_required = args_count
                    break
            
            if not is_re_function:
                raise SyntaxError(f'ExprStr: function \'{node.func.id}\' is not supported.')
        
        if not is_re_function:
            args_required = self.functions[node.func.id]

        if len(node.args) != args_required:
            raise SyntaxError( 'ExprStr: function \'{}\' takes exactly {} arguments, but {} provided.'
                .format(node.func.id, args_required, len(node.args)))

        self.stack.append(node.func.id)

        for arg in node.args[::-1]:
            self.visit(arg)

    def visit_IfExp(self, node: ast.IfExp) -> Any:
        self.stack.append('?')

        self.visit(node.orelse)
        self.visit(node.body)
        self.visit(node.test)


    def __str__(self) -> str:
        return ' '.join(self.stack[::-1])
        

def extract_planes(clip: vs.VideoNode, plane_format: vs.Format = vs.GRAY) -> List[vs.VideoNode]:
    """
    Extracts clip's planes as list.

    Usage:

    ``y, u, v = extract_planes(clip)``

    ``y, *_   = extract_planes(clip)``

    ``_, u, v = extract_planes(clip)``

    :param VideoNode clip: Clip to work with
    :param Format plane_format: Format to use for each extracted plane
    :return: List with every plane of clip in order they're stored
    :rtype: List[VideoNode]
    """

    planes = []
    for i in range(clip.format.num_planes):
        planes.append(core.std.ShufflePlanes(clip, i, plane_format))
    return planes
