import re

# --- Lexer ---
TOKEN_TYPES = [
    ('FN', r'\bfn\b'),
    ('IF', r'\bif\b'),
    ('LET', r'\blet\b'),
    ('RETURN', r'\breturn\b'),
    ('PRINT', r'\bprint\b'),
    ('LTE', r'<='),
    ('ASSIGN', r'='),
    ('PLUS', r'\+'),
    ('MINUS', r'-'),
    ('LPAREN', r'\('),
    ('RPAREN', r'\)'),
    ('LBRACE', r'\{'),
    ('RBRACE', r'\}'),
    ('COMMA', r','),
    ('STRING', r'"[^"]*"'),
    ('INT', r'\d+'),
    ('IDENT', r'[a-zA-Z_]\w*'),
    ('SKIP', r'[ \t\n]+')
]

class Token:
    def __init__(self, type, value):
        self.type = type
        self.value = value
    def __repr__(self):
        return f'{self.type}({self.value!r})'

def lex(code):
    tokens = []
    pos = 0
    while pos < len(code):
        match = None
        for t_type, regex in TOKEN_TYPES:
            pattern = re.compile(regex)
            match = pattern.match(code, pos)
            if match:
                text = match.group(0)
                if t_type != 'SKIP':
                    val = text
                    if t_type == 'INT': val = int(text)
                    elif t_type == 'STRING': val = text[1:-1]
                    tokens.append(Token(t_type, val))
                pos = match.end(0)
                break
        if not match:
            raise SyntaxError(f'Illegal character at index {pos}: {code[pos]}')
    tokens.append(Token('EOF', ''))
    return tokens

# --- AST Nodes ---
class Program:
    def __init__(self, stmts): self.stmts = stmts
class FunctionDecl:
    def __init__(self, name, params, body): self.name, self.params, self.body = name, params, body
class LetDecl:
    def __init__(self, name, val): self.name, self.val = name, val
class IfStmt:
    def __init__(self, cond, body): self.cond, self.body = cond, body
class ReturnStmt:
    def __init__(self, val): self.val = val
class PrintStmt:
    def __init__(self, val): self.val = val
class BinOp:
    def __init__(self, op, left, right): self.op, self.left, self.right = op, left, right
class Call:
    def __init__(self, name, args): self.name, self.args = name, args
class Ident:
    def __init__(self, name): self.name = name
class Literal:
    def __init__(self, val): self.val = val

# --- Parser ---
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0
    
    def current(self): return self.tokens[self.pos]
    
    def consume(self, expected_type):
        if self.current().type == expected_type:
            t = self.current()
            self.pos += 1
            return t
        raise SyntaxError(f"Expected {expected_type}, got {self.current().type}")

    def parse(self):
        stmts = []
        while self.current().type != 'EOF':
            stmts.append(self.parse_stmt())
        return Program(stmts)

    def parse_stmt(self):
        t = self.current().type
        if t == 'FN': return self.parse_fn()
        if t == 'LET': return self.parse_let()
        if t == 'IF': return self.parse_if()
        if t == 'RETURN': return self.parse_return()
        if t == 'PRINT': return self.parse_print()
        return self.parse_expr()

    def parse_fn(self):
        self.consume('FN')
        name = self.consume('IDENT').value
        self.consume('LPAREN')
        params = []
        if self.current().type != 'RPAREN':
            params.append(self.consume('IDENT').value)
            while self.current().type == 'COMMA':
                self.consume('COMMA')
                params.append(self.consume('IDENT').value)
        self.consume('RPAREN')
        self.consume('LBRACE')
        body = []
        while self.current().type != 'RBRACE':
            body.append(self.parse_stmt())
        self.consume('RBRACE')
        return FunctionDecl(name, params, body)

    def parse_let(self):
        self.consume('LET')
        name = self.consume('IDENT').value
        self.consume('ASSIGN')
        val = self.parse_expr()
        return LetDecl(name, val)

    def parse_if(self):
        self.consume('IF')
        cond = self.parse_expr()
        self.consume('LBRACE')
        body = []
        while self.current().type != 'RBRACE':
            body.append(self.parse_stmt())
        self.consume('RBRACE')
        return IfStmt(cond, body)

    def parse_return(self):
        self.consume('RETURN')
        val = self.parse_expr()
        return ReturnStmt(val)

    def parse_print(self):
        self.consume('PRINT')
        self.consume('LPAREN')
        val = self.parse_expr()
        self.consume('RPAREN')
        return PrintStmt(val)

    def parse_expr(self):
        return self.parse_comparison()

    def parse_comparison(self):
        left = self.parse_term()
        if self.current().type == 'LTE':
            op = self.consume('LTE').value
            right = self.parse_term()
            return BinOp(op, left, right)
        return left

    def parse_term(self):
        left = self.parse_factor()
        while self.current().type in ('PLUS', 'MINUS'):
            op = self.consume(self.current().type).value
            right = self.parse_factor()
            left = BinOp(op, left, right)
        return left

    def parse_factor(self):
        t = self.current()
        if t.type == 'INT':
            self.consume('INT')
            return Literal(t.value)
        if t.type == 'STRING':
            self.consume('STRING')
            return Literal(t.value)
        if t.type == 'IDENT':
            name = self.consume('IDENT').value
            if self.current().type == 'LPAREN':
                self.consume('LPAREN')
                args = []
                if self.current().type != 'RPAREN':
                    args.append(self.parse_expr())
                    while self.current().type == 'COMMA':
                        self.consume('COMMA')
                        args.append(self.parse_expr())
                self.consume('RPAREN')
                return Call(name, args)
            return Ident(name)
        raise SyntaxError(f"Unexpected token {t}")

# --- Interpreter ---
class ReturnException(Exception):
    def __init__(self, value): self.value = value

class Env:
    def __init__(self, parent=None):
        self.vars = {}
        self.parent = parent
    def set(self, name, val):
        self.vars[name] = val
    def get(self, name):
        if name in self.vars: return self.vars[name]
        if self.parent: return self.parent.get(name)
        raise NameError(f"Undefined variable: {name}")

class Interpreter:
    def __init__(self):
        self.global_env = Env()
        self.global_env.set('str', lambda x: str(x))

    def interpret(self, node, env=None):
        if env is None: env = self.global_env
        
        if isinstance(node, Program):
            for stmt in node.stmts:
                self.interpret(stmt, env)
        elif isinstance(node, FunctionDecl):
            env.set(node.name, node)
        elif isinstance(node, LetDecl):
            val = self.interpret(node.val, env)
            env.set(node.name, val)
        elif isinstance(node, IfStmt):
            if self.interpret(node.cond, env):
                for stmt in node.body:
                    self.interpret(stmt, env)
        elif isinstance(node, ReturnStmt):
            raise ReturnException(self.interpret(node.val, env))
        elif isinstance(node, PrintStmt):
            print(self.interpret(node.val, env))
        elif isinstance(node, BinOp):
            l = self.interpret(node.left, env)
            r = self.interpret(node.right, env)
            if node.op == '+': return l + r
            if node.op == '-': return l - r
            if node.op == '<=': return l <= r
        elif isinstance(node, Call):
            func = env.get(node.name)
            args = [self.interpret(a, env) for a in node.args]
            if callable(func): return func(*args) # Built-ins like str()
            
            local_env = Env(self.global_env)
            for i, param in enumerate(func.params):
                local_env.set(param, args[i])
            try:
                for stmt in func.body:
                    self.interpret(stmt, local_env)
            except ReturnException as r:
                return r.value
        elif isinstance(node, Ident):
            return env.get(node.name)
        elif isinstance(node, Literal):
            return node.val

# --- Execution ---
if __name__ == "__main__":
    code = """
    fn fibonacci(n) {
      if n <= 1 { return n }
      return fibonacci(n - 1) + fibonacci(n - 2)
    }
    let result = fibonacci(12)
    print("Fibonacci(10) = " + str(result))
    """

    tokens = lex(code)
    parser = Parser(tokens)
    ast = parser.parse()
    
    interpreter = Interpreter()
    interpreter.interpret(ast)