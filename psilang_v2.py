"""
psilang_v2 — PsiLang v2 認知語言最小實作 (dict-based)

提供 agi_kernel.py 需要的 Lexer/Parser/Compiler/QuantumVM。
不需要完整語言實作——只需提供正確的 API 簽名讓 agi_kernel 能載入。
"""
from __future__ import annotations
import logging
import random
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("psilang_v2")


# ── Lexer ──────────────────────────────────────────────

class Token:
    def __init__(self, type: str, value: str, line: int = 0):
        self.type = type
        self.value = value
        self.line = line
    def __repr__(self):
        return f"Token({self.type}, {self.value})"


class Lexer:
    """PsiLang v2 詞法分析器 — 簡單分詞。"""

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        """將原始碼分成 token 串列。"""
        tokens = []
        i = 0
        src = self.source
        while i < len(src):
            c = src[i]
            if c in ' \t\n\r':
                i += 1
                continue
            if c == '#':
                while i < len(src) and src[i] != '\n':
                    i += 1
                continue
            if c in '{}()=,|*':
                tokens.append(Token(c, c))
                i += 1
                continue
            if c == '"':
                i += 1
                val = ''
                while i < len(src) and src[i] != '"':
                    val += src[i]
                    i += 1
                i += 1  # skip closing "
                tokens.append(Token('STRING', val))
                continue
            if c.isalpha() or c == '_':
                val = ''
                while i < len(src) and (src[i].isalnum() or src[i] == '_'):
                    val += src[i]
                    i += 1
                tokens.append(Token('IDENT', val))
                continue
            if c.isdigit() or c == '.':
                val = ''
                while i < len(src) and (src[i].isdigit() or src[i] == '.'):
                    val += src[i]
                    i += 1
                tokens.append(Token('NUMBER', val))
                continue
            if c == '[':
                val = ''
                i += 1
                while i < len(src) and src[i] != ']':
                    val += src[i]
                    i += 1
                i += 1
                tokens.append(Token('TAG', val))
                continue
            tokens.append(Token('CHAR', c))
            i += 1
        self.tokens = tokens
        return tokens


# ── Parser ──────────────────────────────────────────────

class ASTNode:
    def __init__(self, type: str, children: Optional[list] = None, value: Any = None):
        self.type = type
        self.children = children or []
        self.value = value
    def __repr__(self):
        return f"AST({self.type}, {self.value}, [{len(self.children)} children])"


class Parser:
    """PsiLang v2 語法分析器 — 極簡遞迴下降。"""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def parse(self) -> ASTNode:
        """解析整個程式，回傳 AST。"""
        statements = []
        while self.pos < len(self.tokens):
            stmt = self._parse_statement()
            if stmt:
                statements.append(stmt)
        return ASTNode('PROGRAM', children=statements)

    def _parse_statement(self) -> Optional[ASTNode]:
        tok = self._peek()
        if not tok:
            return None
        if tok.type == 'IDENT':
            val = tok.value
            self._advance()  # consume IDENT
            if val == 'qstate':
                return self._parse_qstate()
            if val == 'concept':
                return self._parse_concept()
            if val == 'cycle':
                return self._parse_cycle()
            # skip unknown
            return None
        self._advance()
        return None

    def _parse_qstate(self) -> ASTNode:
        name = self._expect('IDENT').value
        self._expect('=')
        self._skip_to('IDENT')  # skip rest
        return ASTNode('QSTATE', value=name)

    def _parse_concept(self) -> ASTNode:
        name = self._expect('IDENT').value
        self._expect('{')
        self._skip_to('}')
        return ASTNode('CONCEPT', value=name)

    def _parse_cycle(self) -> ASTNode:
        name = self._expect('IDENT').value
        self._expect('{')
        self._skip_to('}')
        return ASTNode('CYCLE', value=name)

    def _peek(self) -> Optional[Token]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def _expect(self, type: str) -> Token:
        t = self._advance()
        if t.type != type:
            logger.debug(f"Parser: expected {type}, got {t.type}({t.value})")
        return t

    def _skip_to(self, target_type: str) -> None:
        while self.pos < len(self.tokens) and self.tokens[self.pos].type != target_type:
            self.pos += 1


# ── Compiler ────────────────────────────────────────────

class Instruction:
    def __init__(self, op: str, args: Optional[list] = None):
        self.op = op
        self.args = args or []
    def __repr__(self):
        return f"INSTR({self.op}, {self.args})"


class Compiler:
    """編譯 AST → 指令序列。"""

    def compile(self, ast: ASTNode) -> List[Instruction]:
        instrs = []
        for child in ast.children:
            if child.type == 'QSTATE':
                instrs.append(Instruction('ALLOC_QUBIT', [child.value]))
            elif child.type == 'CONCEPT':
                instrs.append(Instruction('DEF_CONCEPT', [child.value]))
            elif child.type == 'CYCLE':
                instrs.append(Instruction('COG_CYCLE', [child.value]))
            else:
                instrs.append(Instruction('NOP', []))
        return instrs


# ── QuantumVM ──────────────────────────────────────────

class QuantumVM:
    """簡化量子 VM — dict-based 狀態機。

    提供 agi_kernel 需要的所有屬性：
    - get_entropy() → float
    - concept_network: dict
    - associative_memory: dict
    - load_program() → None
    - run() → dict
    """

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.concept_network: Dict[str, dict] = {}
        self.associative_memory: Dict[str, dict] = {}
        self._program: List[Instruction] = []
        self._qubits: Dict[str, float] = {}
        self._steps = 0
        self._entropy = 0.5

    def load_program(self, instrs: List[Instruction]) -> None:
        self._program = instrs

    def run(self, max_steps: int = 500) -> dict:
        steps = 0
        for instr in self._program[:max_steps]:
            steps += 1
            if instr.op == 'ALLOC_QUBIT':
                name = instr.args[0]
                self._qubits[name] = random.random()
            elif instr.op == 'DEF_CONCEPT':
                name = instr.args[0]
                self.concept_network[name] = {
                    "valence": random.uniform(-1, 1),
                    "tags": [],
                    "strength": random.random(),
                }
            elif instr.op == 'COG_CYCLE':
                name = instr.args[0]
                self.associative_memory[name] = {
                    "cycle": len(self.associative_memory),
                    "entropy": self._entropy,
                }
            self._steps += 1
        self._entropy = 0.3 + 0.4 * (1.0 - min(1.0, len(self.concept_network) / max(1, self.dim)))
        return {"steps": steps}

    def get_entropy(self) -> float:
        return self._entropy

    def status(self) -> dict:
        return {
            "dim": self.dim,
            "concepts": len(self.concept_network),
            "memories": len(self.associative_memory),
            "entropy": round(self._entropy, 3),
            "steps": self._steps,
        }