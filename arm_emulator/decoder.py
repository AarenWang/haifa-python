"""AArch64 解码器（反汇编器）。

从 4 字节二进制解析出 Instruction 对象。
按 AArch64 编码格式逐位匹配指令类型。

参考：ARM Architecture Reference Manual ARMv8-A
"""

from __future__ import annotations

from .instructions import (
    Condition,
    EncodingFormat,
    ImmediateOperand,
    Instruction,
    LabelOperand,
    MemoryOperand,
    Mnemonic,
    RegisterOperand,
    ShiftType,
    ShiftedOperand,
    decode_register,
    extract_bits,
    sign_extend,
)


class DecodeError(Exception):
    """解码失败。"""

    def __init__(self, word: int, message: str = "") -> None:
        self.word = word
        super().__init__(
            f"{message} (word=0x{word & 0xFFFFFFFF:08x})"
            if message
            else f"cannot decode word 0x{word & 0xFFFFFFFF:08x}"
        )


def decode(word: int) -> Instruction:
    """解码 32 位指令。"""
    word = word & 0xFFFFFFFF

    for decoder_fn in (
        _try_decode_branch,
        _try_decode_movw,
        _try_decode_add_sub_immediate,
        _try_decode_csel,
        _try_decode_load_store,
        _try_decode_add_sub_register,
        _try_decode_logical_register,
        _try_decode_dp_2src,
        _try_decode_dp_3src,
        _try_decode_halt,
    ):
        result = decoder_fn(word)
        if result is not None:
            return result

    raise DecodeError(word)


# ============================================================
# 分支指令
# ============================================================

def _try_decode_branch(word: int) -> Instruction | None:
    # B: 000101 | imm26
    if extract_bits(word, 26, 6) == 0b000101:
        imm26 = extract_bits(word, 0, 26)
        offset = sign_extend(imm26, 26) * 4
        return Instruction(
            Mnemonic.B,
            (LabelOperand(f"+{offset}" if offset >= 0 else str(offset), offset),),
            raw_word=word,
        )

    # BL: 100101 | imm26
    if extract_bits(word, 26, 6) == 0b100101:
        imm26 = extract_bits(word, 0, 26)
        offset = sign_extend(imm26, 26) * 4
        return Instruction(
            Mnemonic.BL,
            (LabelOperand(f"+{offset}" if offset >= 0 else str(offset), offset),),
            raw_word=word,
        )

    # B.cond: 0101010 0 | imm19 | 0 | cond
    if extract_bits(word, 24, 8) == 0b01010100:
        imm19 = extract_bits(word, 5, 19)
        cond_code = extract_bits(word, 0, 4)
        cond = Condition.from_code(cond_code)
        offset = sign_extend(imm19, 19) * 4
        return Instruction(
            Mnemonic.B_COND,
            (LabelOperand(f"+{offset}" if offset >= 0 else str(offset), offset),),
            raw_word=word,
            condition=cond,
        )

    # unconditional branch (register): bits[31:25] = 1101011
    if extract_bits(word, 25, 7) == 0b1101011:
        op1 = extract_bits(word, 21, 3)
        rn = extract_bits(word, 5, 5)
        op2 = extract_bits(word, 0, 5)

        if op1 == 0b000 and op2 == 0b00000:
            return Instruction(
                Mnemonic.BR,
                (RegisterOperand(rn, True),),
                raw_word=word,
            )
        if op1 == 0b001 and op2 == 0b00000:
            return Instruction(
                Mnemonic.BLR,
                (RegisterOperand(rn, True),),
                raw_word=word,
            )
        if op1 == 0b010 and op2 == 0b00000:
            if rn == 30:
                return Instruction(Mnemonic.RET, (), raw_word=word)
            return Instruction(
                Mnemonic.RET,
                (RegisterOperand(rn, True),),
                raw_word=word,
            )

    return None


# ============================================================
# MOVZ/MOVN/MOVK
# ============================================================

def _try_decode_movw(word: int) -> Instruction | None:
    if extract_bits(word, 23, 6) != 0b100101:
        return None

    sf = extract_bits(word, 31, 1)
    opc = extract_bits(word, 29, 2)
    imm16 = extract_bits(word, 5, 16)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    if opc == 0b00:
        return Instruction(Mnemonic.MOVN, (RegisterOperand(rd, is_64bit), ImmediateOperand(imm16)), raw_word=word)
    if opc == 0b10:
        return Instruction(Mnemonic.MOVZ, (RegisterOperand(rd, is_64bit), ImmediateOperand(imm16)), raw_word=word)
    if opc == 0b11:
        return Instruction(Mnemonic.MOVK, (RegisterOperand(rd, is_64bit), ImmediateOperand(imm16)), raw_word=word)
    return None


# ============================================================
# ADD/SUB 立即数
# ============================================================

def _try_decode_add_sub_immediate(word: int) -> Instruction | None:
    if extract_bits(word, 23, 6) != 0b100010:
        return None

    sf = extract_bits(word, 31, 1)
    op = extract_bits(word, 30, 1)
    s = extract_bits(word, 29, 1)
    sh = extract_bits(word, 22, 1)
    imm12 = extract_bits(word, 10, 12)
    rn = extract_bits(word, 5, 5)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    actual_imm = imm12 << (12 if sh else 0)

    if op == 0 and s == 0:
        mnemonic = Mnemonic.ADD
    elif op == 0 and s == 1:
        mnemonic = Mnemonic.CMN if rd == 31 else Mnemonic.ADDS
    elif op == 1 and s == 0:
        mnemonic = Mnemonic.SUB
    elif op == 1 and s == 1:
        mnemonic = Mnemonic.CMP if rd == 31 else Mnemonic.SUBS
    else:
        return None

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    imm_op = ImmediateOperand(actual_imm)

    if mnemonic in (Mnemonic.CMP, Mnemonic.CMN):
        return Instruction(mnemonic, (rn_op, imm_op), raw_word=word)
    return Instruction(mnemonic, (rd_op, rn_op, imm_op), raw_word=word)


# ============================================================
# 条件选择 (CSEL/CSINC)
# ============================================================

def _try_decode_csel(word: int) -> Instruction | None:
    if extract_bits(word, 21, 10) != 0b0011010100:
        return None

    sf = extract_bits(word, 31, 1)
    rm = extract_bits(word, 16, 5)
    cond_code = extract_bits(word, 12, 4)
    op2 = extract_bits(word, 10, 2)
    rn = extract_bits(word, 5, 5)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)
    cond = Condition.from_code(cond_code)

    if op2 == 0b00:  # CSEL
        return Instruction(
            Mnemonic.CSEL,
            (RegisterOperand(rd, is_64bit), RegisterOperand(rn, is_64bit), RegisterOperand(rm, is_64bit)),
            raw_word=word,
            condition=cond,
        )

    if op2 == 0b01:  # CSINC / CSET
        if rn == 31 and rm == 31:
            return Instruction(
                Mnemonic.CSET,
                (RegisterOperand(rd, is_64bit),),
                raw_word=word,
                condition=cond,
            )
        return Instruction(
            Mnemonic.CSINC,
            (RegisterOperand(rd, is_64bit), RegisterOperand(rn, is_64bit), RegisterOperand(rm, is_64bit)),
            raw_word=word,
            condition=cond,
        )

    return None


# ============================================================
# Load/Store
# ============================================================

def _try_decode_load_store(word: int) -> Instruction | None:
    if extract_bits(word, 27, 3) != 0b111:
        return None
    if extract_bits(word, 26, 1) != 0:
        return None
    if extract_bits(word, 24, 2) != 0b01:
        return None

    size = extract_bits(word, 30, 2)
    opc = extract_bits(word, 22, 2)
    imm12 = extract_bits(word, 10, 12)
    rn = extract_bits(word, 5, 5)
    rt = extract_bits(word, 0, 5)

    if size == 0b11:
        is_64bit = True
        load = bool(opc & 1)
    elif size == 0b10:
        is_64bit = False
        load = bool(opc & 1)
    else:
        return None

    is_signed = bool(opc & 0b10)
    if is_signed and not load:
        return None

    base = RegisterOperand(rn, True)
    offset = imm12 * (1 << size) if size >= 2 else sign_extend(imm12, 12) * (1 << size)
    mem_op = MemoryOperand(base, offset=offset)

    if load:
        return Instruction(Mnemonic.LDR, (RegisterOperand(rt, is_64bit), mem_op), raw_word=word)
    return Instruction(Mnemonic.STR, (RegisterOperand(rt, is_64bit), mem_op), raw_word=word)


# ============================================================
# ADD/SUB (寄存器, shifted register)
# ============================================================

def _try_decode_add_sub_register(word: int) -> Instruction | None:
    """add/subtract (shifted register): bits[28:24] = 01011, bit[21] = 0."""
    if extract_bits(word, 24, 5) != 0b01011:
        return None
    if extract_bits(word, 21, 1) != 0:
        return None

    sf = extract_bits(word, 31, 1)
    op = extract_bits(word, 30, 1)
    s = extract_bits(word, 29, 1)
    shift_type = extract_bits(word, 22, 2)
    rm = extract_bits(word, 16, 5)
    imm6 = extract_bits(word, 10, 6)
    rn = extract_bits(word, 5, 5)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    rm_op = RegisterOperand(rm, is_64bit)

    if imm6 == 0 and shift_type == 0:
        rm_shifted = rm_op
    else:
        rm_shifted = ShiftedOperand(rm_op, ShiftType.from_code(shift_type), imm6)

    if op == 0 and s == 0:
        return Instruction(Mnemonic.ADD, (rd_op, rn_op, rm_shifted), raw_word=word)
    if op == 0 and s == 1:
        if rd == 31:
            return Instruction(Mnemonic.CMN, (rn_op, rm_shifted), raw_word=word)
        return Instruction(Mnemonic.ADDS, (rd_op, rn_op, rm_shifted), raw_word=word)
    if op == 1 and s == 0:
        return Instruction(Mnemonic.SUB, (rd_op, rn_op, rm_shifted), raw_word=word)
    if op == 1 and s == 1:
        if rd == 31:
            return Instruction(Mnemonic.CMP, (rn_op, rm_shifted), raw_word=word)
        return Instruction(Mnemonic.SUBS, (rd_op, rn_op, rm_shifted), raw_word=word)
    return None


# ============================================================
# 逻辑指令 (shifted register)
# ============================================================

def _try_decode_logical_register(word: int) -> Instruction | None:
    """logical (shifted register): bits[28:24] = 01010."""
    if extract_bits(word, 24, 5) != 0b01010:
        return None

    sf = extract_bits(word, 31, 1)
    opc = extract_bits(word, 29, 2)
    n = extract_bits(word, 21, 1)
    shift_type = extract_bits(word, 22, 2)
    rm = extract_bits(word, 16, 5)
    imm6 = extract_bits(word, 10, 6)
    rn = extract_bits(word, 5, 5)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    rm_op = RegisterOperand(rm, is_64bit)

    if imm6 == 0 and shift_type == 0:
        rm_shifted = rm_op
    else:
        rm_shifted = ShiftedOperand(rm_op, ShiftType.from_code(shift_type), imm6)

    # MOV = ORR Xd, XZR, Xm
    if opc == 0b01 and n == 0 and rn == 31:
        return Instruction(Mnemonic.MOV, (rd_op, rm_shifted), raw_word=word)

    # MVN = ORN Xd, XZR, Xm
    if opc == 0b01 and n == 1 and rn == 31:
        return Instruction(Mnemonic.MVN, (rd_op, rm_shifted), raw_word=word)

    if opc == 0b00 and n == 0:
        return Instruction(Mnemonic.AND, (rd_op, rn_op, rm_shifted), raw_word=word)
    if opc == 0b11 and n == 0:
        return Instruction(Mnemonic.ANDS, (rd_op, rn_op, rm_shifted), raw_word=word)
    if opc == 0b01 and n == 0:
        return Instruction(Mnemonic.ORR, (rd_op, rn_op, rm_shifted), raw_word=word)
    if opc == 0b10 and n == 0:
        return Instruction(Mnemonic.EOR, (rd_op, rn_op, rm_shifted), raw_word=word)
    return None


# ============================================================
# 数据处理 (2 source): SDIV/UDIV/LSLV/LSRV/ASRV/RORV
# ============================================================

def _try_decode_dp_2src(word: int) -> Instruction | None:
    """data processing (2 source): bits[30:21] = 0011010110."""
    if extract_bits(word, 21, 10) != 0b0011010110:
        return None

    sf = extract_bits(word, 31, 1)
    rm = extract_bits(word, 16, 5)
    opcode = extract_bits(word, 10, 6)
    rn = extract_bits(word, 5, 5)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    rm_op = RegisterOperand(rm, is_64bit)

    table = {
        0b000010: Mnemonic.UDIV,
        0b000011: Mnemonic.SDIV,
        0b001000: Mnemonic.LSL,
        0b001001: Mnemonic.LSR,
        0b001010: Mnemonic.ASR,
        0b001011: Mnemonic.ROR,
    }

    mnem = table.get(opcode)
    if mnem is not None:
        return Instruction(mnem, (rd_op, rn_op, rm_op), raw_word=word)
    return None


# ============================================================
# 数据处理 (3 source): MUL/MADD/MSUB
# ============================================================

def _try_decode_dp_3src(word: int) -> Instruction | None:
    """data processing (3 source): bits[30:29]=00, bits[28:24]=11011."""
    if extract_bits(word, 29, 1) != 0:
        return None
    if extract_bits(word, 30, 1) != 0:
        return None
    if extract_bits(word, 24, 5) != 0b11011:
        return None

    sf = extract_bits(word, 31, 1)
    o0 = extract_bits(word, 21, 3)  # [23:21]
    ra = extract_bits(word, 16, 5)  # [20:16]
    rm = extract_bits(word, 11, 5)  # [15:11]
    rn = extract_bits(word, 5, 5)   # [9:5]
    rd = extract_bits(word, 0, 5)   # [4:0]
    is_64bit = bool(sf)

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    rm_op = RegisterOperand(rm, is_64bit)

    if o0 == 0b000:
        # MADD: Rd = Ra + Rn * Rm
        if ra == 31:
            # MUL: Rd = Rn * Rm (Ra = XZR)
            return Instruction(Mnemonic.MUL, (rd_op, rn_op, rm_op), raw_word=word)
    return None


# ============================================================
# HALT 伪指令
# ============================================================

HALT_ENCODING = 0x00000000


def _try_decode_halt(word: int) -> Instruction | None:
    if word == HALT_ENCODING:
        return Instruction(Mnemonic.HALT, (), raw_word=word)
    return None
