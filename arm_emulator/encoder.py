"""AArch64 汇编器（编码器）。

从文本汇编生成 4 字节二进制编码。

支持：
- 寄存器名（X0-X30, W0-W30, XZR, WZR, SP, LR, FP）
- 立即数（十进制、十六进制 0x）
- 标签定义与引用
- 移位修饰（LSL/LSR/ASR/ROR）
- 内存操作数（[Xn], [Xn, #imm], [Xn, #imm]!, [Xn], #imm）
- 伪指令（.word, .skip, .string, HALT, NOP）

两遍扫描：
- 第一遍：收集标签地址
- 第二遍：生成编码，解析标签引用为偏移量
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .instructions import (
    Condition,
    EncodingFormat,
    Mnemonic,
    ShiftType,
    build_add_sub_immediate,
    build_b,
    build_b_cond,
    build_bl,
    build_movz,
    encode_register,
    extract_bits,
    insert_bits,
    mask_bits,
    sign_extend,
)


class AssembleError(Exception):
    """汇编错误。"""


@dataclass
class AssembleResult:
    """汇编结果。"""
    words: list[int] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)
    base_addr: int = 0


# 助记符到编码器的映射表
_MNEMONIC_TABLE: dict[str, Any] = {}


def _register(*names: str):
    """装饰器：注册助记符处理器。"""
    def decorator(func):
        for name in names:
            _MNEMONIC_TABLE[name.upper()] = func
        return func
    return decorator


def assemble(text: str, *, base_addr: int = 0) -> AssembleResult:
    """汇编文本代码。

    Args:
        text: 汇编源码
        base_addr: 程序加载基址

    Returns:
        AssembleResult: 包含编码后的 32 位字列表和标签地址表

    Raises:
        AssembleError: 语法错误或编码失败
    """
    lines = _preprocess(text)
    labels: dict[str, int] = {}
    items: list[tuple[int, str, list[str]]] = []  # (addr, mnemonic, operands)

    # --- 第一遍：收集标签地址 ---
    addr = base_addr
    for line_no, raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # 标签定义
        if line.endswith(":"):
            label = line[:-1].strip()
            if not label:
                raise AssembleError(f"line {line_no}: empty label")
            if label in labels:
                raise AssembleError(f"line {line_no}: duplicate label '{label}'")
            labels[label] = addr
            continue

        # 标签 + 指令在同一行
        if ":" in line and not line.startswith("."):
            parts = line.split(":", 1)
            label = parts[0].strip()
            if label and not any(c in label for c in " \t,[]#"):
                if label in labels:
                    raise AssembleError(f"line {line_no}: duplicate label '{label}'")
                labels[label] = addr
                line = parts[1].strip()
                if not line:
                    continue

        # 伪指令 .word/.skip/.string 占用不同大小
        if line.upper().startswith(".WORD"):
            count = 1
        elif line.upper().startswith(".SKIP"):
            parts = line.split()
            count = int(_parse_imm(parts[1])) // 4 if len(parts) > 1 else 0
        elif line.upper().startswith(".STRING"):
            # .string "hello" → 向上取整到 4 字节
            raw = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else '""'
            s = _parse_string(raw)
            count = (len(s) + 3) // 4
        else:
            count = 1

        mnemonic, operands = _parse_instruction(line)
        items.append((addr, mnemonic, operands))
        addr += count * 4

    # --- 第二遍：生成编码 ---
    result = AssembleResult(labels=labels, base_addr=base_addr)
    for item_addr, mnemonic, operands in items:
        if mnemonic.startswith("."):
            words = _assemble_pseudo(mnemonic, operands, item_addr, labels, base_addr)
        else:
            words = [_assemble_instruction(mnemonic, operands, item_addr, labels, base_addr)]
        result.words.extend(words)

    return result


# ============================================================
# 预处理
# ============================================================

def _preprocess(text: str) -> list[tuple[int, str]]:
    """去除注释和空行，返回 (行号, 内容) 列表。"""
    result = []
    for line_no, line in enumerate(text.splitlines(), 1):
        # 去除注释
        comment_pos = _find_comment(line)
        if comment_pos >= 0:
            line = line[:comment_pos]
        line = line.strip()
        if line:
            result.append((line_no, line))
    return result


def _find_comment(line: str) -> int:
    """找到注释开始位置（; 或 //），忽略字符串内的。"""
    in_string = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == '"':
            in_string = not in_string
        elif not in_string and c == ";":
            return i
        elif not in_string and c == "/" and i + 1 < len(line) and line[i + 1] == "/":
            return i
        i += 1
    return -1


# ============================================================
# 解析
# ============================================================

def _parse_instruction(line: str) -> tuple[str, list[str]]:
    """解析一行指令，返回 (助记符, 操作数列表)。"""
    # 分割助记符和操作数
    parts = line.split(None, 1)
    mnemonic = parts[0].upper()
    if len(parts) == 1:
        return mnemonic, []

    operand_str = parts[1]
    operands = _split_operands(operand_str)
    return mnemonic, operands


def _split_operands(s: str) -> list[str]:
    """分割操作数字符串，处理括号内的逗号。"""
    operands = []
    current = []
    depth = 0
    in_string = False

    for c in s:
        if c == '"':
            in_string = not in_string
            current.append(c)
        elif in_string:
            current.append(c)
        elif c == "[":
            depth += 1
            current.append(c)
        elif c == "]":
            depth -= 1
            current.append(c)
        elif c == "," and depth == 0:
            operands.append("".join(current).strip())
            current = []
        else:
            current.append(c)

    if current:
        last = "".join(current).strip()
        if last:
            operands.append(last)

    return operands


def _parse_imm(s: str) -> int:
    """解析立即数（十进制或十六进制）。"""
    s = s.strip()
    if s.startswith("#"):
        s = s[1:]
    s = s.strip()
    try:
        if s.lower().startswith("0x"):
            return int(s, 16)
        if s.lower().startswith("-0x"):
            return -int(s[1:], 16)
        return int(s, 10)
    except ValueError:
        raise AssembleError(f"invalid immediate: {s!r}")


def _parse_string(s: str) -> str:
    """解析带引号的字符串。"""
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    raise AssembleError(f"invalid string literal: {s!r}")


def _parse_register(s: str) -> int:
    """解析寄存器名，返回编号。"""
    try:
        return encode_register(s.strip())
    except ValueError:
        raise AssembleError(f"invalid register: {s!r}")


def _parse_condition(s: str) -> Condition:
    """解析条件码。"""
    try:
        return Condition.from_name(s.strip())
    except ValueError:
        raise AssembleError(f"invalid condition: {s!r}")


def _resolve_label_or_imm(s: str, current_addr: int, labels: dict[str, int], base_addr: int) -> int:
    """解析标签引用或立即数。"""
    s = s.strip()
    if s.startswith("#"):
        return _parse_imm(s)
    if s in labels:
        return labels[s]
    # 尝试作为立即数
    return _parse_imm(s)


# ============================================================
# 指令编码器
# ============================================================

def _assemble_instruction(
    mnemonic: str,
    operands: list[str],
    current_addr: int,
    labels: dict[str, int],
    base_addr: int,
) -> int:
    """编码单条指令。"""
    handler = _MNEMONIC_TABLE.get(mnemonic)
    if handler is None:
        raise AssembleError(f"unknown mnemonic: {mnemonic}")
    return handler(operands, current_addr, labels, base_addr)


# --- MOVZ/MOVN/MOVK ---

@_register("MOVZ")
def _encode_movz(operands, current_addr, labels, base_addr):
    if len(operands) < 2:
        raise AssembleError("MOVZ requires Rd, #imm16")
    rd = _parse_register(operands[0])
    imm16 = _parse_imm(operands[1])
    hw = 0
    if len(operands) >= 4:
        shift_name = operands[2].strip().upper()
        shift_amt = _parse_imm(operands[3])
        if shift_name == "LSL":
            hw = shift_amt // 16
    return build_movz(rd, imm16, hw=hw, is_64bit=True)


@_register("MOVN")
def _encode_movn(operands, current_addr, labels, base_addr):
    if len(operands) < 2:
        raise AssembleError("MOVN requires Rd, #imm16")
    rd = _parse_register(operands[0])
    imm16 = _parse_imm(operands[1])
    hw = 0
    if len(operands) >= 4:
        shift_name = operands[2].strip().upper()
        shift_amt = _parse_imm(operands[3])
        if shift_name == "LSL":
            hw = shift_amt // 16
    # MOVN 编码: opc=00
    word = build_movz(rd, imm16, hw=hw, is_64bit=True)
    # 修改 opc 为 00
    word = insert_bits(word, 29, 2, 0b00)
    return word


@_register("MOVK")
def _encode_movk(operands, current_addr, labels, base_addr):
    if len(operands) < 2:
        raise AssembleError("MOVK requires Rd, #imm16")
    rd = _parse_register(operands[0])
    imm16 = _parse_imm(operands[1])
    hw = 0
    if len(operands) >= 4:
        shift_name = operands[2].strip().upper()
        shift_amt = _parse_imm(operands[3])
        if shift_name == "LSL":
            hw = shift_amt // 16
    # MOVK 编码: opc=11
    word = build_movz(rd, imm16, hw=hw, is_64bit=True)
    word = insert_bits(word, 29, 2, 0b11)
    return word


# --- ADD/SUB/CMP/CMN ---

@_register("ADD", "ADDS", "SUB", "SUBS", "CMP", "CMN", "NEG", "NEGS")
def _encode_add_sub(operands, current_addr, labels, base_addr):
    mnem = _encode_add_sub._current_mnemonic  # type: ignore
    # 这里需要用不同方式处理
    pass


# 分别注册
@_register("ADD")
def _encode_add(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("ADD requires Rd, Rn, Rm/#imm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    # 判断第三操作数是立即数还是寄存器
    third = operands[2].strip()
    if third.startswith("#"):
        imm12 = _parse_imm(third)
        return build_add_sub_immediate(rd, rn, imm12, is_sub=False, set_flags=False)
    else:
        # 寄存器 ADD
        rm = _parse_register(third)
        return _build_add_sub_register(rd, rn, rm, is_sub=False, set_flags=False)


@_register("ADDS")
def _encode_adds(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("ADDS requires Rd, Rn, Rm/#imm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    third = operands[2].strip()
    if third.startswith("#"):
        imm12 = _parse_imm(third)
        return build_add_sub_immediate(rd, rn, imm12, is_sub=False, set_flags=True)
    else:
        rm = _parse_register(third)
        return _build_add_sub_register(rd, rn, rm, is_sub=False, set_flags=True)


@_register("SUB")
def _encode_sub(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("SUB requires Rd, Rn, Rm/#imm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    third = operands[operands.index(operands[2]) if len(operands) > 2 else 0].strip()
    if third.startswith("#"):
        imm12 = _parse_imm(third)
        return build_add_sub_immediate(rd, rn, imm12, is_sub=True, set_flags=False)
    else:
        rm = _parse_register(third)
        return _build_add_sub_register(rd, rn, rm, is_sub=True, set_flags=False)


@_register("SUBS")
def _encode_subs(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("SUBS requires Rd, Rn, Rm/#imm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    third = operands[2].strip()
    if third.startswith("#"):
        imm12 = _parse_imm(third)
        return build_add_sub_immediate(rd, rn, imm12, is_sub=True, set_flags=True)
    else:
        rm = _parse_register(third)
        return _build_add_sub_register(rd, rn, rm, is_sub=True, set_flags=True)


@_register("CMP")
def _encode_cmp(operands, current_addr, labels, base_addr):
    if len(operands) != 2:
        raise AssembleError("CMP requires Rn, Rm/#imm")
    rn = _parse_register(operands[0])
    second = operands[1].strip()
    if second.startswith("#"):
        imm12 = _parse_imm(second)
        return build_add_sub_immediate(31, rn, imm12, is_sub=True, set_flags=True)
    else:
        rm = _parse_register(second)
        return _build_add_sub_register(31, rn, rm, is_sub=True, set_flags=True)


@_register("CMN")
def _encode_cmn(operands, current_addr, labels, base_addr):
    if len(operands) != 2:
        raise AssembleError("CMN requires Rn, Rm/#imm")
    rn = _parse_register(operands[0])
    second = operands[1].strip()
    if second.startswith("#"):
        imm12 = _parse_imm(second)
        return build_add_sub_immediate(31, rn, imm12, is_sub=False, set_flags=True)
    else:
        rm = _parse_register(second)
        return _build_add_sub_register(31, rn, rm, is_sub=False, set_flags=True)


@_register("NEG", "NEGS")
def _encode_neg(operands, current_addr, labels, base_addr):
    is_s = operands[0].upper().endswith("S") if operands else False
    # 实际这里 mnem 已经被注册为 NEG 或 NEGS
    pass


def _build_add_sub_register(
    rd: int, rn: int, rm: int,
    *, is_sub: bool = False, set_flags: bool = False, is_64bit: bool = True,
) -> int:
    """编码 ADD/SUB（寄存器）。

    格式: sf | op | S | 01011 | shift | 0 | Rm | imm6 | Rn | Rd
    """
    word = 0
    word = insert_bits(word, 31, 1, int(is_64bit))
    word = insert_bits(word, 30, 1, int(is_sub))
    word = insert_bits(word, 29, 1, int(set_flags))
    word = insert_bits(word, 24, 5, 0b01011)  # bits[28:24]
    word = insert_bits(word, 22, 2, 0)  # shift type = LSL
    word = insert_bits(word, 21, 1, 0)  # bit 21 = 0
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 10, 6, 0)  # imm6 = 0 (no shift)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


# 重新注册 NEG/NEGS（因为装饰器方式有问题）
@_register("NEG")
def _encode_neg2(operands, current_addr, labels, base_addr):
    if len(operands) != 2:
        raise AssembleError("NEG requires Rd, Rm/#imm")
    rd = _parse_register(operands[0])
    second = operands[1].strip()
    if second.startswith("#"):
        imm12 = _parse_imm(second)
        return build_add_sub_immediate(rd, 31, imm12, is_sub=True, set_flags=False)
    else:
        rm = _parse_register(second)
        return _build_add_sub_register(rd, 31, rm, is_sub=True, set_flags=False)


@_register("NEGS")
def _encode_negs2(operands, current_addr, labels, base_addr):
    if len(operands) != 2:
        raise AssembleError("NEGS requires Rd, Rm/#imm")
    rd = _parse_register(operands[0])
    second = operands[1].strip()
    if second.startswith("#"):
        imm12 = _parse_imm(second)
        return build_add_sub_immediate(rd, 31, imm12, is_sub=True, set_flags=True)
    else:
        rm = _parse_register(second)
        return _build_add_sub_register(rd, 31, rm, is_sub=True, set_flags=True)


# --- MOV ---

@_register("MOV")
def _encode_mov(operands, current_addr, labels, base_addr):
    """MOV Xd, Xm → ORR Xd, XZR, Xm"""
    if len(operands) != 2:
        raise AssembleError("MOV requires Rd, Rm")
    rd = _parse_register(operands[0])
    rm = _parse_register(operands[1])
    return _build_logical_register(rd, 31, rm, opc=0b01, is_64bit=True)


# --- 逻辑指令 ---

def _build_logical_register(
    rd: int, rn: int, rm: int,
    *, opc: int = 0b01, is_64bit: bool = True,
) -> int:
    """编码逻辑指令（寄存器）。

    格式: sf | opc | 01010 | shift | N | Rm | imm6 | Rn | Rd
    opc: 00=AND, 01=ORR, 10=EOR
    N: 0 for AND/ORR/EOR, 1 for ANDS/BIC/ORN/EON
    """
    word = 0
    word = insert_bits(word, 31, 1, int(is_64bit))
    word = insert_bits(word, 29, 2, opc)
    word = insert_bits(word, 24, 5, 0b01010)
    word = insert_bits(word, 22, 2, 0)  # shift type = LSL
    word = insert_bits(word, 21, 1, 0)  # N = 0
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 10, 6, 0)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


@_register("AND")
def _encode_and(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("AND requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_logical_register(rd, rn, rm, opc=0b00)


@_register("ANDS")
def _encode_ands(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("ANDS requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_logical_register(rd, rn, rm, opc=0b11)


@_register("ORR")
def _encode_orr(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("ORR requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_logical_register(rd, rn, rm, opc=0b01)


@_register("EOR")
def _encode_eor(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("EOR requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_logical_register(rd, rn, rm, opc=0b10)


@_register("MVN")
def _encode_mvn(operands, current_addr, labels, base_addr):
    """MVN Xd, Xm → ORN Xd, XZR, Xm"""
    if len(operands) != 2:
        raise AssembleError("MVN requires Rd, Rm")
    rd = _parse_register(operands[0])
    rm = _parse_register(operands[1])
    word = _build_logical_register(rd, 31, rm, opc=0b01)
    word = insert_bits(word, 21, 1, 1)  # N=1 for ORN
    return word


# --- 移位指令 ---

def _build_shift_register(
    rd: int, rn: int, rm: int, *, shift: int = 0, is_64bit: bool = True,
) -> int:
    """编码 LSL/LSR/ASR/ROR（寄存器变体）。

    格式: sf | 0 | S | 11010110 | Rm | op2 | Rn | Rd
    op2: 00=LSL, 01=LSR, 10=ASR, 11=ROR
    """
    word = 0
    word = insert_bits(word, 31, 1, int(is_64bit))
    word = insert_bits(word, 30, 1, 0)  # op = 0
    word = insert_bits(word, 29, 1, 0)  # S = 0
    word = insert_bits(word, 24, 5, 0b11010)
    word = insert_bits(word, 21, 3, 0b110)  # bits[23:21] = 110
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 10, 6, shift)  # op2 in bits[15:10]
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


@_register("LSL")
def _encode_lsl(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("LSL requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_shift_register(rd, rn, rm, shift=0b001000)


@_register("LSR")
def _encode_lsr(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("LSR requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_shift_register(rd, rn, rm, shift=0b001001)


@_register("ASR")
def _encode_asr(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("ASR requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_shift_register(rd, rn, rm, shift=0b001010)


@_register("ROR")
def _encode_ror(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("ROR requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    return _build_shift_register(rd, rn, rm, shift=0b001011)


# --- MUL ---

@_register("MUL")
def _encode_mul(operands, current_addr, labels, base_addr):
    """MUL Rd, Rn, Rm → MADD Rd, Rn, Rm, XZR"""
    if len(operands) != 3:
        raise AssembleError("MUL requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    # MADD: sf | 00 | 11011 | 000 | Ra | Rm | 0 | Rn | Rd
    word = 0
    word = insert_bits(word, 31, 1, 1)  # sf=1 (64-bit)
    word = insert_bits(word, 24, 5, 0b11011)
    word = insert_bits(word, 21, 3, 0b000)
    word = insert_bits(word, 16, 5, 31)  # Ra = XZR
    word = insert_bits(word, 11, 5, rm)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


# --- SDIV/UDIV ---

@_register("SDIV")
def _encode_sdiv(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("SDIV requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    # SDIV: sf | 0 | 0 | 11010110 | Rm | 000011 | Rn | Rd
    word = 0
    word = insert_bits(word, 31, 1, 1)
    word = insert_bits(word, 24, 5, 0b11010)
    word = insert_bits(word, 21, 3, 0b110)
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 10, 6, 0b000011)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


@_register("UDIV")
def _encode_udiv(operands, current_addr, labels, base_addr):
    if len(operands) != 3:
        raise AssembleError("UDIV requires Rd, Rn, Rm")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    # UDIV: sf | 0 | 0 | 11010110 | Rm | 000010 | Rn | Rd
    word = 0
    word = insert_bits(word, 31, 1, 1)
    word = insert_bits(word, 24, 5, 0b11010)
    word = insert_bits(word, 21, 3, 0b110)
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 10, 6, 0b000010)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


# --- 条件选择 ---

@_register("CSEL")
def _encode_csel(operands, current_addr, labels, base_addr):
    if len(operands) != 4:
        raise AssembleError("CSEL requires Rd, Rn, Rm, cond")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    cond = _parse_condition(operands[3])
    # CSEL: sf | 00 | 11010100 | Rm | cond | 00 | Rn | Rd
    word = 0
    word = insert_bits(word, 31, 1, 1)
    word = insert_bits(word, 21, 10, 0b0011010100)
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 12, 4, cond.code)
    word = insert_bits(word, 10, 2, 0b00)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


@_register("CSET")
def _encode_cset(operands, current_addr, labels, base_addr):
    """CSET Rd, cond → CSINC Rd, XZR, XZR, invert(cond)"""
    if len(operands) != 2:
        raise AssembleError("CSET requires Rd, cond")
    rd = _parse_register(operands[0])
    cond = _parse_condition(operands[1])
    inverted = cond.code ^ 1  # 反转最低位
    # CSINC: sf | 00 | 11010100 | Rm | cond | 01 | Rn | Rd
    word = 0
    word = insert_bits(word, 31, 1, 1)
    word = insert_bits(word, 21, 10, 0b0011010100)
    word = insert_bits(word, 16, 5, 31)  # Rm = XZR
    word = insert_bits(word, 12, 4, inverted)
    word = insert_bits(word, 10, 2, 0b01)
    word = insert_bits(word, 5, 5, 31)  # Rn = XZR
    word = insert_bits(word, 0, 5, rd)
    return word


@_register("CSINC")
def _encode_csinc(operands, current_addr, labels, base_addr):
    if len(operands) != 4:
        raise AssembleError("CSINC requires Rd, Rn, Rm, cond")
    rd = _parse_register(operands[0])
    rn = _parse_register(operands[1])
    rm = _parse_register(operands[2])
    cond = _parse_condition(operands[3])
    word = 0
    word = insert_bits(word, 31, 1, 1)
    word = insert_bits(word, 21, 10, 0b0011010100)
    word = insert_bits(word, 16, 5, rm)
    word = insert_bits(word, 12, 4, cond.code)
    word = insert_bits(word, 10, 2, 0b01)
    word = insert_bits(word, 5, 5, rn)
    word = insert_bits(word, 0, 5, rd)
    return word


# --- 分支指令 ---

@_register("B")
def _encode_b(operands, current_addr, labels, base_addr):
    if len(operands) != 1:
        raise AssembleError("B requires label")
    target = _resolve_label(operands[0], current_addr, labels, base_addr)
    offset = target - current_addr
    return build_b(offset)


@_register("BL")
def _encode_bl(operands, current_addr, labels, base_addr):
    if len(operands) != 1:
        raise AssembleError("BL requires label")
    target = _resolve_label(operands[0], current_addr, labels, base_addr)
    offset = target - current_addr
    return build_bl(offset)


@_register("BR")
def _encode_br(operands, current_addr, labels, base_addr):
    if len(operands) != 1:
        raise AssembleError("BR requires Rn")
    rn = _parse_register(operands[0])
    # BR Xn: 1101011 0000 11111 000000 Rn 00000
    word = 0xD61F0000 | (rn << 5)
    return word


@_register("BLR")
def _encode_blr(operands, current_addr, labels, base_addr):
    if len(operands) != 1:
        raise AssembleError("BLR requires Rn")
    rn = _parse_register(operands[0])
    # BLR Xn: 1101011 0001 11111 000000 Rn 00000
    word = 0xD63F0000 | (rn << 5)
    return word


@_register("RET")
def _encode_ret(operands, current_addr, labels, base_addr):
    # RET (default X30): 1101011 0010 11111 000000 11110 00000
    rn = _parse_register(operands[0]) if operands else 30
    word = 0xD65F0000 | (rn << 5)  # default LR = X30
    return word


def _resolve_label(s: str, current_addr: int, labels: dict[str, int], base_addr: int) -> int:
    """解析分支目标标签。"""
    s = s.strip()
    if s in labels:
        return labels[s]
    # 尝试数字地址
    try:
        return _parse_imm(s)
    except AssembleError:
        raise AssembleError(f"unknown label: {s!r}")


# --- B.cond ---

# B.cond 需要特殊处理，因为助记符包含点号
# 在 _parse_instruction 中 B.EQ 会被解析为 mnemonic="B.EQ"
# 我们在 assemble() 中需要先检查 B.xxx

def _assemble_b_cond(mnemonic: str, operands, current_addr, labels, base_addr):
    """处理 B.cond 指令。"""
    cond_name = mnemonic.split(".", 1)[1]
    cond = _parse_condition(cond_name)
    target = _resolve_label(operands[0], current_addr, labels, base_addr)
    offset = target - current_addr
    return build_b_cond(cond.code, offset)


# --- Load/Store ---

@_register("LDR")
def _encode_ldr(operands, current_addr, labels, base_addr):
    if len(operands) != 2:
        raise AssembleError("LDR requires Rt, [Rn, ...]")
    rt = _parse_register(operands[0])
    base, offset, pre, post = _parse_memory_operand(operands[1])
    size = 0b11  # 64-bit
    # LDR (immediate offset): 11 111 0 01 01 imm12 Rn Rt
    word = 0
    word = insert_bits(word, 30, 2, size)
    word = insert_bits(word, 27, 3, 0b111)
    word = insert_bits(word, 26, 1, 0)
    word = insert_bits(word, 24, 2, 0b01)
    word = insert_bits(word, 22, 2, 0b01)  # opc=01 for LDR
    imm12 = offset // 8  # 64-bit: scale by 8
    word = insert_bits(word, 10, 12, imm12 & mask_bits(12))
    word = insert_bits(word, 5, 5, base)
    word = insert_bits(word, 0, 5, rt)
    return word


@_register("STR")
def _encode_str(operands, current_addr, labels, base_addr):
    if len(operands) != 2:
        raise AssembleError("STR requires Rt, [Rn, ...]")
    rt = _parse_register(operands[0])
    base, offset, pre, post = _parse_memory_operand(operands[1])
    size = 0b11  # 64-bit
    # STR (immediate offset): 11 111 0 01 00 imm12 Rn Rt
    word = 0
    word = insert_bits(word, 30, 2, size)
    word = insert_bits(word, 27, 3, 0b111)
    word = insert_bits(word, 26, 1, 0)
    word = insert_bits(word, 24, 2, 0b01)
    word = insert_bits(word, 22, 2, 0b00)  # opc=00 for STR
    imm12 = offset // 8  # 64-bit: scale by 8
    word = insert_bits(word, 10, 12, imm12 & mask_bits(12))
    word = insert_bits(word, 5, 5, base)
    word = insert_bits(word, 0, 5, rt)
    return word


def _parse_memory_operand(s: str) -> tuple[int, int, bool, bool]:
    """解析内存操作数，返回 (base_reg, offset, pre_indexed, post_indexed)。"""
    s = s.strip()
    pre_indexed = False
    post_indexed = False

    # 后索引: [Xn], #imm
    if "]" in s and s.index("]") < len(s) - 1:
        # 找到 ] 的位置
        bracket_close = s.index("]")
        base_part = s[1:bracket_close].strip()
        rest = s[bracket_close + 1:].strip().lstrip(",").strip()
        base = _parse_register(base_part)
        offset = _parse_imm(rest) if rest else 0
        post_indexed = True
        return base, offset, False, True

    # 前索引: [Xn, #imm]!
    if s.endswith("!"):
        s = s[:-1].strip()
        pre_indexed = True

    # [Xn] 或 [Xn, #imm]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        parts = [p.strip() for p in inner.split(",")]
        base = _parse_register(parts[0])
        offset = _parse_imm(parts[1]) if len(parts) > 1 else 0
        return base, offset, pre_indexed, False

    raise AssembleError(f"invalid memory operand: {s!r}")


# --- 伪指令 ---

@_register("HALT")
def _encode_halt(operands, current_addr, labels, base_addr):
    return 0x00000000


@_register("NOP")
def _encode_nop(operands, current_addr, labels, base_addr):
    # NOP = HINT #0 = 1101010100 0 00 011 0010 0000 000 11111
    return 0xD503201F


def _assemble_pseudo(
    mnemonic: str,
    operands: list[str],
    current_addr: int,
    labels: dict[str, int],
    base_addr: int,
) -> list[int]:
    """汇编伪指令。"""
    mnem = mnemonic.upper()

    if mnem == ".WORD":
        result = []
        for op in operands:
            result.append(_parse_imm(op) & 0xFFFFFFFF)
        return result

    if mnem == ".SKIP":
        size = _parse_imm(operands[0]) if operands else 0
        num_words = size // 4
        return [0] * num_words

    if mnem == ".STRING":
        s = _parse_string(operands[0]) if operands else ""
        data = s.encode("utf-8")
        # 填充到 4 字节对齐
        while len(data) % 4 != 0:
            data += b"\x00"
        result = []
        for i in range(0, len(data), 4):
            word = int.from_bytes(data[i:i+4], "little")
            result.append(word)
        return result

    raise AssembleError(f"unknown pseudo-instruction: {mnemonic}")


# ============================================================
# 补丁：B.cond 处理
# ============================================================

# 覆盖 _assemble_instruction 以处理 B.cond
_original_assemble_instruction = _assemble_instruction


def _assemble_instruction(mnemonic: str, operands, current_addr, labels, base_addr):
    if mnemonic.startswith("B."):
        return _assemble_b_cond(mnemonic, operands, current_addr, labels, base_addr)
    return _original_assemble_instruction(mnemonic, operands, current_addr, labels, base_addr)
