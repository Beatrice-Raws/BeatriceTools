import ast
import re
from typing import Any, List, overload

import vapoursynth as vs
from vapoursynth import core


class ExprStr(ast.NodeVisitor):
    """
    Drop-in wrapper for Expr() string in infix form.

    Usage:

    ``core.std.Expr((clip1, clip2), ExprStr('x * 0.5 + y * 0.5'))``

    ``ExprStr((clip1, clip2), 'x * 0.5 + y * 0.5')``

    Almost all operators and functions of Expr are supported,
    but input string must contain a valid Python expression,
    therefore syntax slightly differs:
    1. Parentheses ``()`` are used to order operations.
    2. Equality operator is ``==``.
    3. Python conditional expression ``b if a else c`` replaces
       conditional operator ``?``.
    4. Stack manipulation functions swap() and dup() are not supported.
    5. XOR (exclusive-or) logical operator is not supported.

    More examples:

    ``>>> print(ExprStr('50 if a < b and b < c else 0'))``

    ``a b > c < d >=``

    ``>>> print(ExprStr('abs(sqrt(a) * (0 if b < 100 else c), e)'))``

    ``a sqrt b 100 < 0 c ? * e abs``
    """

    variables = 'abcdefghijklmnopqrstuvwxyz'

    # Available operators and their Expr respresentation
    operators = {
        ast.Add:  '+',
        ast.Sub:  '-',
        ast.Mult: '*',
        ast.Div:  '/',

        ast.Eq:   '=',
        ast.Gt:   '>',
        ast.Lt:   '<',
        ast.GtE: '>=',
        ast.LtE: '<=',

        ast.Not: 'not',
        ast.And: 'and',
        ast.Or:  'or',
        # ???: 'xor',
    }

    # Avaialable fixed-name functions and number of their arguments
    functions = {
        'abs':  1,
        'exp':  1,
        'log':  1,
        'sqrt': 1,

        'max': 2,
        'min': 2,
        'pow': 2,
    }

    # Available functions with names defined as regexp and number of their
    # arguments
    functions_re = {
        # re.compile(r'dup\d*') : 1,
        # re.compile(r'swap\d*'): 2,
    }

    @overload
    def __new__(cls, string: str) -> 'ExprStr': ...
    @overload
    def __new__(cls, *args: Any, **kwargs: Any) -> vs.VideoNode: ...

    def __new__(cls, *args, **kwargs):
        if len(args) == 0 and len(kwargs) == 0:
            raise TypeError

        if len(args) == 1 and isinstance(args[0], str):
            filter_mode = False
            string = args[0]
        elif len(kwargs) == 1 and 'string' in kwargs:
            filter_mode = False
            string = kwargs['string']
        else:
            filter_mode = True
            if len(args) > 1:
                string = args[1]
            else:
                string = kwargs['string']

        obj = object.__new__(cls)
        obj.__init__(string)

        if filter_mode:
            if len(args) > 1:
                new_args = list(args)
                new_args[1] = str(obj)
                return core.std.Expr(*new_args, **kwargs)
            else:
                kwargs['string'] = str(obj)
                return core.std.Expr(*args, **kwargs)
        else:
            return obj

    def __init__(self, string: str):
        self.stack: List[str] = []
        # 'eval' mode takes care of assignment operator
        self.visit(ast.parse(string, mode='eval'))

    def visit_Num(self, node: ast.Num) -> None:
        self.stack.append(str(node.n))

    def visit_Name(self, node: ast.Name) -> None:
        if (len(node.id) > 1
                or node.id not in self.variables):
            raise SyntaxError(
                'ExprStr: clip name "{}" at column {} is not valid.'
                .format(node.id, node.col_offset))

        self.stack.append(node.id)

    def visit_Compare(self, node: ast.Compare) -> Any:
        if len(node.ops) > 1:
            raise SyntaxError(
                'ExprStr: chaining of comparison operators at column {}'
                ' is not supported'.format(node.col_offset))
        op = node.ops[0]

        if type(op) not in self.operators:
            raise SyntaxError(
                'ExprStr: operator "{}" at column {} is not supported.'
                .format(op, node.col_offset))
        self.stack.append(self.operators[type(op)])
        self.visit(node.comparators[0])
        self.visit(node.left)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        if type(node.op) not in self.operators:
            raise SyntaxError(
                'ExprStr: operator "{}" at column {} is not supported.'
                .format(type(node.op), node.col_offset))
        self.stack.append(self.operators[type(node.op)])
        self.visit(node.operand)

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        if type(node.op) not in self.operators:
            raise SyntaxError(
                'ExprStr: operator "{}" at column {} is not supported.'
                .format(type(node.op), node.col_offset))

        self.stack.append(self.operators[type(node.op)])

        self.visit(node.values[0])
        self.visit(node.values[1])

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if type(node.op) not in self.operators:
            raise SyntaxError(
                'ExprStr: operator "{}" at column {} is not supported.'
                .format(type(node.op), node.col_offset))

        self.stack.append(self.operators[type(node.op)])

        self.visit(node.right)
        self.visit(node.left)

    def visit_Call(self, node: ast.Call) -> Any:
        import re

        is_re_function = False
        args_required = 0
        if node.func.id not in self.functions:
            for pattern, args_count in self.functions_re.items():
                if pattern.fullmatch(node.func.id):
                    is_re_function = True
                    args_required = args_count
                    break

            if not is_re_function:
                raise SyntaxError(
                    'ExprStr: function "{}" at column {} is not supported.'
                    .format(node.func.id, node.col_offset))

        if not is_re_function:
            args_required = self.functions[node.func.id]

        if len(node.args) != args_required:
            raise SyntaxError(
                'ExprStr: function "{}" at column {}'
                ' takes exactly {} arguments, but {} provided.'
                .format(node.func.id, node.col_offset, args_required,
                        len(node.args)))

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


def extract_planes(clip: vs.VideoNode, plane_format: vs.Format = vs.GRAY) \
        -> List[vs.VideoNode]:
    """
    Extracts clip's planes as list.

    Usage:

    ``y, u, v = extract_planes(clip)``

    ``y, *_   = extract_planes(clip)``

    ``_, u, v = extract_planes(clip)``

    :param VideoNode clip: Clip to work with.
    :param Format plane_format: Format to use for each extracted plane.
    :return: List with every plane of clip in order they're stored.
    """
    return [core.std.ShufflePlanes(clip, i, plane_format)
            for i in range(clip.format.num_planes)]
