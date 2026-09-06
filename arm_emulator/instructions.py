"""AArch64 指令定义：编码格式常量、枚举、bit-field 工具。

参照 ARM Architecture Reference Manual (ARMv8-A) 定义：
- 指令类型枚举与助记符映射
- 各指令的 bit-field 编码常量
- 位域提取/拼接/符号扩展工具函数
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ============================================================
# 位宽常量
# ============================================================

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1
MASK16 = (1 << 16) - 1
MASK12 = (1 << 12) - 1
MASK6 = (1 << 6) - 1
MASK5 = (1 << 5) - 1


# ============================================================
# bit-field 工具函数
# ============================================================

def extract_bits(value: int, start: int, width: int) -> int:
    """从 value 的第 start 位开始提取 width 位的无符号值。

    bit 0 是最低位（LSB）。

    示例：
        extract_bits(0b10110, 1, 3) == 0b011  # 从 bit1 开始取 3 位
    """
    return (value >> start) & ((1 << width) - 1)


def insert_bits(value: int, start: int, width: int, field_value: int) -> int:
    """将 field_value 的低 width 位写入 value 的第 start 位开始的位置。

    示例：
        insert_bits(0b10000, 0, 3, 0b111) == 0b10111
    """
    mask = ((1 << width) - 1) << start
    cleared = value & ~mask
    return cleared | ((field_value & ((1 << width) - 1)) << start)


def sign_extend(value: int, bits: int) -> int:
    """将 bits 位宽的值进行符号扩展。

    如果最高位为 1，则高位填充 1（返回负数）。

    示例：
        sign_extend(0b1111, 4) == -1
        sign_extend(0b0111, 4) == 7
    """
    sign_bit = 1 << (bits - 1)
    if value & sign_bit:
        return value - (1 << bits)
    return value


def mask_bits(width: int) -> int:
    """返回 width 位的全 1 掩码。"""
    return (1 << width) - 1


# ============================================================
# 寄存器编号工具
# ============================================================

def encode_register(name: str) -> int:
    """将寄存器名（X0-X30, W0-W30, XZR, WZR, SP）编码为 5 位编号。

    X0-X30 → 0-30, XZR → 31
    W0-W30 → 0-30, WZR → 31
    SP → 31（在 load/store 上下文中）
    """
    name = name.strip().upper()
    if name in ("XZR", "WZR"):
        return 31
    if name == "SP":
        return 31
    if name.startswith("X") and name[1:].isdigit():
        idx = int(name[1:])
        if 0 <= idx <= 30:
            return idx
    if name.startswith("W") and name[1:].isdigit():
        idx = int(name[1:])
        if 0 <= idx <= 30:
            return idx
    raise ValueError(f"cannot encode register name: {name!r}")


def decode_register(index: int, is_64bit: bool = True) -> str:
    """将 5 位编号解码为寄存器名。

    index 31: 64 位返回 XZR, 32 位返回 WZR
    index 0-30: 64 位返回 Xn, 32 位返回 Wn
    """
    if index < 0 or index > 31:
        raise ValueError(f"register index out of range: {index}")
    if index == 31:
        return "XZR" if is_64bit else "WZR"
    prefix = "X" if is_64bit else "W"
    return f"{prefix}{index}"


# ============================================================
# 条件码枚举
# ============================================================

class Condition(Enum):
    """AArch64 的 16 种条件码。"""

    EQ = 0x0   # Z == 1
    NE = 0x1   # Z == 0
    CS = 0x2   # C == 1 (同 HS)
    CC = 0x3   # C == 0 (同 LO)
    MI = 0x4   # N == 1
    PL = 0x5   # N == 0
    VS = 0x6   # V == 1
    VC = 0x7   # V == 0
    HI = 0x8   # C == 1 and Z == 0
    LS = 0x9   # C == 0 or Z == 1
    GE = 0xA   # N == V
    LT = 0xB   # N != V
    GT = 0xC   # Z == 0 and N == V
    LE = 0xD   # Z == 1 or N != V
    AL = 0xE   # always
    NV = 0xF   # never

    @property
    def code(self) -> int:
        return self.value

    @classmethod
    def from_name(cls, name: str) -> "Condition":
        name = name.strip().upper()
        if name == "HS":
            return cls.CS
        if name == "LO":
            return cls.CC
        try:
            return cls[name]
        except KeyError:
            raise ValueError(f"unknown condition: {name!r}")

    @classmethod
    def from_code(cls, code: int) -> "Condition":
        for cond in cls:
            if cond.value == code:
                return cond
        raise ValueError(f"unknown condition code: {code}")

    @property
    def name_str(self) -> str:
        """返回汇编语法中的条件名（HS/LO 替换 CS/CC）。"""
        if self == Condition.CS:
            return "CS"
        if self == Condition.CC:
            return "CC"
        return self.name


# ============================================================
# 移位类型枚举
# ============================================================

class ShiftType(Enum):
    """AArch64 数据处理指令的移位类型。"""

    LSL = 0x0  # 逻辑左移
    LSR = 0x1  # 逻辑右移
    ASR = 0x2  # 算术右移
    ROR = 0x3  # 循环右移

    @classmethod
    def from_name(cls, name: str) -> "ShiftType":
        name = name.strip().upper()
        try:
            return cls[name]
        except KeyError:
            raise ValueError(f"unknown shift type: {name!r}")

    @classmethod
    def from_code(cls, code: int) -> "ShiftType":
        for st in cls:
            if st.value == code:
                return st
        raise ValueError(f"unknown shift code: {code}")


# ============================================================
# 扩展类型枚举（用于 LDR/STR 的 extend 修饰）
# ============================================================

class ExtendType(Enum):
    """AArch64 load/store 的寄存器扩展类型。"""

    UXTB = 0x0
    UXTH = 0x1
    UXTW = 0x2
    UXTX = 0x3
    SXTB = 0x4
    SXTH = 0x5
    SXTW = 0x6
    SXTX = 0x7

    @classmethod
    def from_name(cls, name: str) -> "ExtendType":
        name = name.strip().upper()
        try:
            return cls[name]
        except KeyError:
            raise ValueError(f"unknown extend type: {name!r}")

    @classmethod
    def from_code(cls, code: int) -> "ExtendType":
        for et in cls:
            if et.value == code:
                return et
        raise ValueError(f"unknown extend code: {code}")


# ============================================================
# 指令类型枚举
# ============================================================

class Mnemonic(Enum):
    """AArch64 第一阶段指令助记符。"""

    # 数据处理 — 算术
    ADD = auto()
    ADDS = auto()
    SUB = auto()
    SUBS = auto()
    MUL = auto()
    SDIV = auto()
    UDIV = auto()
    CMP = auto()      # SUBS 别名
    CMN = auto()      # ADDS 别名
    NEG = auto()      # SUB 别名
    NEGS = auto()     # SUBS 别名

    # 数据处理 — 逻辑与移位
    AND = auto()
    ANDS = auto()
    ORR = auto()
    EOR = auto()
    MOV = auto()      # ORR 别名
    MVN = auto()      # ORN 别名
    LSL = auto()      # LSLV / UBFM 别名
    LSR = auto()      # LSRV / UBFM 别名
    ASR = auto()      # ASRV / SBFM 别名
    ROR = auto()      # RORV 别名

    # 立即数加载
    MOVZ = auto()
    MOVN = auto()
    MOVK = auto()

    # 条件选择
    CSEL = auto()
    CSET = auto()     # CSINC 别名
    CSINC = auto()

    # 控制流
    B = auto()
    BL = auto()
    BR = auto()
    BLR = auto()
    RET = auto()
    B_COND = auto()   # B.cond

    # Load / Store
    STR = auto()
    LDR = auto()
    STP = auto()
    LDP = auto()

    # 伪指令
    HALT = auto()     # 教学伪指令
    NOP = auto()      # 伪指令


# ============================================================
# 指令操作数类型
# ============================================================

@dataclass(frozen=True)
class RegisterOperand:
    """寄存器操作数。"""
    index: int          # 0-31
    is_64bit: bool      # True=Xn, False=Wn

    def __str__(self) -> str:
        return decode_register(self.index, self.is_64bit)


@dataclass(frozen=True)
class ImmediateOperand:
    """立即数操作数。"""
    value: int

    def __str__(self) -> str:
        if self.value < 0:
            return f"#{self.value}"
        return f"#0x{self.value:x}" if self.value > 255 else f"#{self.value}"


@dataclass(frozen=True)
class ShiftedOperand:
    """带移位修饰的操作数（用于数据处理指令）。"""
    register: RegisterOperand
    shift_type: ShiftType
    shift_amount: int   # 0-63 (64位) 或 0-31 (32位)

    def __str__(self) -> str:
        if self.shift_amount == 0 and self.shift_type == ShiftType.LSL:
            return str(self.register)
        return f"{self.register}, {self.shift_type.name} #{self.shift_amount}"


@dataclass(frozen=True)
class MemoryOperand:
    """内存操作数（用于 LDR/STR）。"""
    base: RegisterOperand
    offset: int = 0
    index_reg: RegisterOperand | None = None
    pre_indexed: bool = False    # [Xn, #imm]!
    post_indexed: bool = False   # [Xn], #imm

    def __str__(self) -> str:
        if self.index_reg is not None:
            return f"[{self.base}, {self.index_reg}]"
        if self.post_indexed:
            return f"[{self.base}], #{self.offset}"
        if self.pre_indexed:
            return f"[{self.base}, #{self.offset}]!"
        if self.offset == 0:
            return f"[{self.base}]"
        return f"[{self.base}, #{self.offset}]"


@dataclass(frozen=True)
class LabelOperand:
    """标签/分支目标操作数。"""
    name: str
    offset: int = 0  # 相对偏移（字节），用于已解析的分支

    def __str__(self) -> str:
        return self.name


# ============================================================
# 指令数据类
# ============================================================

@dataclass(frozen=True)
class Instruction:
    """解码后的 AArch64 指令。

    Attributes:
        mnemonic: 助记符
        operands: 操作数列表
        raw_word: 原始 32 位编码
        condition: 条件码（仅 B.cond 使用）
    """
    mnemonic: Mnemonic
    operands: tuple[Any, ...] = ()
    raw_word: int = 0
    condition: Condition | None = None

    def __str__(self) -> str:
        parts = [self.mnemonic.name]
        if self.condition is not None and self.mnemonic == Mnemonic.B_COND:
            parts[0] = f"B.{self.condition.name_str}"
        if self.operands:
            parts.append(", ".join(str(op) for op in self.operands))
        return " ".join(parts)


# ============================================================
# 指令编码格式常量
# ============================================================

class EncodingFormat:
    """AArch64 指令编码格式的 bit-field 位置常量。

    所有常量都是 (start, width) 元组。
    参考：ARM Architecture Reference Manual ARMv8-A
    """

    # --- 通用字段 ---
    SF = (31, 1)          # 1=64位, 0=32位

    # --- 数据处理（立即数）---
    # ADD/SUB 立即数: sf | op | S | 100010 | sh | imm12 | Rn | Rd
    DP_IMM_ADD_SUB_OP = (30, 1)  # 0=ADD, 1=SUB
    DP_IMM_ADD_SUB_S = (29, 1)   # 1=更新标志
    DP_IMM_FIXED = (23, 6)       # 固定位 100010
    DP_IMM_SH = (22, 1)          # 移位: 0=无, 1=LSL#12
    DP_IMM_IMM12 = (10, 12)
    DP_IMM_RN = (5, 5)
    DP_IMM_RD = (0, 5)

    # 逻辑立即数: sf | opc | 100100 | N | immr | imms | Rn | Rd
    DP_IMM_LOGIC_OPC = (29, 2)  # 00=AND, 01=ORR, 10=EOR, 11=ANDS
    DP_IMM_LOGIC_N = (22, 1)
    DP_IMM_LOGIC_IMMR = (16, 6)
    DP_IMM_LOGIC_IMMS = (10, 6)

    # --- 数据处理（寄存器）---
    DP_REG_RM = (16, 5)
    DP_REG_SHIFT_TYPE = (22, 2)
    DP_REG_IMM6 = (10, 6)
    DP_REG_RN = (5, 5)
    DP_REG_RD = (0, 5)

    # --- MOVZ/MOVN/MOVK ---
    # sf | opc | 100101 | hw | imm16 | Rd
    MOVW_OPC = (29, 2)   # 00=MOVN, 10=MOVZ, 11=MOVK
    MOVW_HW = (21, 2)    # 移位量 /16
    MOVW_IMM16 = (5, 16)
    MOVW_RD = (0, 5)

    # --- 条件选择 (CSEL) ---
    CSEL_RM = (16, 5)
    CSEL_COND = (12, 4)
    CSEL_OP2 = (10, 2)   # 00=CSEL, 01=CSINC
    CSEL_RN = (5, 5)
    CSEL_RD = (0, 5)

    # --- 分支 ---
    # B: 000101 | imm26
    B_IMM26 = (0, 26)
    # BL: 100101 | imm26
    BL_IMM26 = (0, 26)
    # B.cond: 0101010 0 | imm19 | 0 | cond
    BCOND_IMM19 = (5, 19)
    BCOND_COND = (0, 4)
    # BR: 1101011 0000 11111 000000 Rn 00000
    BR_RN = (5, 5)

    # --- Load/Store ---
    LS_SIZE = (30, 2)     # 00=8bit, 01=16bit, 10=32bit, 11=64bit
    LS_IMM12 = (10, 12)
    LS_RN = (5, 5)
    LS_RT = (0, 5)


# ============================================================
# 编码辅助函数
# ============================================================

def _put(word: int, field: tuple[int, int], value: int) -> int:
    """将 value 写入 word 中 field=(start, width) 指定的位置。"""
    start, width = field
    return insert_bits(word, start, width, value)


def build_add_sub_immediate(
    rd: int,
    rn: int,
    imm12: int,
    *,
    is_sub: bool = False,
    set_flags: bool = False,
    is_64bit: bool = True,
    shift: bool = False,
) -> int:
    """编码 ADD/SUB/ADDS/SUBS（立即数）。

    返回 32 位编码。
    """
    word = 0
    word = _put(word, EncodingFormat.SF, int(is_64bit))
    word = _put(word, EncodingFormat.DP_IMM_ADD_SUB_OP, int(is_sub))
    word = _put(word, EncodingFormat.DP_IMM_ADD_SUB_S, int(set_flags))
    word = _put(word, EncodingFormat.DP_IMM_FIXED, 0b100010)
    word = _put(word, EncodingFormat.DP_IMM_SH, int(shift))
    word = _put(word, EncodingFormat.DP_IMM_IMM12, imm12 & MASK12)
    word = _put(word, EncodingFormat.DP_IMM_RN, rn & MASK5)
    word = _put(word, EncodingFormat.DP_IMM_RD, rd & MASK5)
    return word


def build_movz(
    rd: int,
    imm16: int,
    *,
    hw: int = 0,
    is_64bit: bool = True,
) -> int:
    """编码 MOVZ 指令。

    hw: 移位量选择，0=不移位, 1=LSL#16, 2=LSL#32, 3=LSL#48
    """
    word = 0
    word = _put(word, EncodingFormat.SF, int(is_64bit))
    word = _put(word, EncodingFormat.MOVW_OPC, 0b10)  # MOVZ
    # 固定位 100101 at bits[28:23]
    word = insert_bits(word, 23, 6, 0b100101)
    word = _put(word, EncodingFormat.MOVW_HW, hw & 0x3)
    word = _put(word, EncodingFormat.MOVW_IMM16, imm16 & MASK16)
    word = _put(word, EncodingFormat.MOVW_RD, rd & MASK5)
    return word


def build_b(offset_bytes: int) -> int:
    """编码 B 指令。

    offset_bytes: 相对偏移（字节），会被转换为 imm26（以字为单位）。
    """
    if offset_bytes % 4 != 0:
        raise ValueError(f"branch offset must be 4-byte aligned: {offset_bytes}")
    imm26 = (offset_bytes >> 2) & mask_bits(26)
    word = 0b000101 << 26
    word = _put(word, EncodingFormat.B_IMM26, imm26)
    return word


def build_bl(offset_bytes: int) -> int:
    """编码 BL 指令。"""
    if offset_bytes % 4 != 0:
        raise ValueError(f"branch offset must be 4-byte aligned: {offset_bytes}")
    imm26 = (offset_bytes >> 2) & mask_bits(26)
    word = 0b100101 << 26
    word = _put(word, EncodingFormat.BL_IMM26, imm26)
    return word


def build_b_cond(cond: int, offset_bytes: int) -> int:
    """编码 B.cond 指令。"""
    if offset_bytes % 4 != 0:
        raise ValueError(f"branch offset must be 4-byte aligned: {offset_bytes}")
    imm19 = (offset_bytes >> 2) & mask_bits(19)
    word = 0b0101010 << 25  # bits[31:25] = 0101010
    word = insert_bits(word, 24, 1, 0)  # bit 24 = 0
    word = _put(word, EncodingFormat.BCOND_IMM19, imm19)
    word = insert_bits(word, 4, 1, 0)   # bit 4 = 0
    word = _put(word, EncodingFormat.BCOND_COND, cond & 0xF)
    return word
