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
        super().__init__(f"{message} (word=0x{word & 0xFFFFFFFF:08x})" if message else f"cannot decode word 0x{word & 0xFFFFFFFF:08x}")


def decode(word: int) -> Instruction:
    """解码 32 位指令。

    主入口：按 bit-field 模式匹配指令类型。

    Args:
        word: 32 位指令编码

    Returns:
        解码后的 Instruction 对象

    Raises:
        DecodeError: 无法识别的指令
    """
    word = word & 0xFFFFFFFF

    # 尝试各类指令解码
    decoder = _try_decode_branch(word)
    if decoder is not None:
        return decoder

    decoder = _try_decode_movw(word)
    if decoder is not None:
        return decoder

    decoder = _try_decode_add_sub_immediate(word)
    if decoder is not None:
        return decoder

    decoder = _try_decode_csel(word)
    if decoder is not None:
        return decoder

    decoder = _try_decode_load_store(word)
    if decoder is not None:
        return decoder

    decoder = _try_decode_data_processing_register(word)
    if decoder is not None:
        return decoder

    decoder = _try_decode_halt(word)
    if decoder is not None:
        return decoder

    raise DecodeError(word)


# ============================================================
# 分支指令解码
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

    # BR Xn: 1101011 0000 11111 000000 Rn 00000
    if word == 0xD61F0000:
        # RET (default X30)
        rn = extract_bits(word, 5, 5)
        return Instruction(
            Mnemonic.RET,
            (RegisterOperand(rn, True),) if rn != 30 else (),
            raw_word=word,
        )

    # BR Xn: 1101011 0000 11111 000000 Rn 00000
    if extract_bits(word, 10, 22) == 0b1101011000011111000000:
        rn = extract_bits(word, 5, 5)
        return Instruction(
            Mnemonic.BR,
            (RegisterOperand(rn, True),),
            raw_word=word,
        )

    # BLR Xn: 1101011 0001 11111 000000 Rn 00000
    if extract_bits(word, 10, 22) == 0b1101011000111111000000:
        rn = extract_bits(word, 5, 5)
        return Instruction(
            Mnemonic.BLR,
            (RegisterOperand(rn, True),),
            raw_word=word,
        )

    # RET Xn: 1101011 0010 11111 000000 Rn 00000
    if extract_bits(word, 10, 22) == 0b1101011001011111000000:
        rn = extract_bits(word, 5, 5)
        if rn == 30:
            return Instruction(Mnemonic.RET, (), raw_word=word)
        return Instruction(
            Mnemonic.RET,
            (RegisterOperand(rn, True),),
            raw_word=word,
        )

    return None


# ============================================================
# MOVZ/MOVN/MOVK 解码
# ============================================================

def _try_decode_movw(word: int) -> Instruction | None:
    # 检查固定位 bits[28:23] = 100101
    if extract_bits(word, 23, 6) != 0b100101:
        return None

    sf = extract_bits(word, 31, 1)
    opc = extract_bits(word, 29, 2)
    hw = extract_bits(word, 21, 2)
    imm16 = extract_bits(word, 5, 16)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    if opc == 0b00:  # MOVN
        actual_value = ~(imm16 << (hw * 16))
        if not is_64bit:
            actual_value &= 0xFFFFFFFF
        else:
            actual_value &= 0xFFFFFFFFFFFFFFFF
        return Instruction(
            Mnemonic.MOVN,
            (
                RegisterOperand(rd, is_64bit),
                ImmediateOperand(imm16),
            ),
            raw_word=word,
        )

    if opc == 0b10:  # MOVZ
        return Instruction(
            Mnemonic.MOVZ,
            (
                RegisterOperand(rd, is_64bit),
                ImmediateOperand(imm16),
            ),
            raw_word=word,
        )

    if opc == 0b11:  # MOVK
        return Instruction(
            Mnemonic.MOVK,
            (
                RegisterOperand(rd, is_64bit),
                ImmediateOperand(imm16),
            ),
            raw_word=word,
        )

    return None


# ============================================================
# ADD/SUB 立即数解码
# ============================================================

def _try_decode_add_sub_immediate(word: int) -> Instruction | None:
    # 检查固定位 bits[28:23] = 100010
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
        # CMN: Rn=XZR, ADDS
        if rd == 31:
            mnemonic = Mnemonic.CMN
        else:
            mnemonic = Mnemonic.ADDS
    elif op == 1 and s == 0:
        mnemonic = Mnemonic.SUB
    elif op == 1 and s == 1:
        # CMP: Rd=XZR, SUBS
        if rd == 31:
            mnemonic = Mnemonic.CMP
        else:
            mnemonic = Mnemonic.SUBS
    else:
        return None

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    imm_op = ImmediateOperand(actual_imm)

    if mnemonic in (Mnemonic.CMP, Mnemonic.CMN):
        return Instruction(mnemonic, (rn_op, imm_op), raw_word=word)
    return Instruction(mnemonic, (rd_op, rn_op, imm_op), raw_word=word)


# ============================================================
# 条件选择 (CSEL/CSINC) 解码
# ============================================================

def _try_decode_csel(word: int) -> Instruction | None:
    # CSEL: sf | 0 | 0 | 11010100 | Rm | cond | 00 | Rn | Rd
    # CSINC: sf | 0 | 0 | 11010100 | Rm | cond | 01 | Rn | Rd
    # 检查 bits[30:21] = 0011010100
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
            (
                RegisterOperand(rd, is_64bit),
                RegisterOperand(rn, is_64bit),
                RegisterOperand(rm, is_64bit),
            ),
            raw_word=word,
            condition=cond,
        )

    if op2 == 0b01:  # CSINC
        # CSET: CSINC Rd, ZZR, XZR, invert(cond)
        if rn == 31 and rm == 31:
            return Instruction(
                Mnemonic.CSET,
                (RegisterOperand(rd, is_64bit),),
                raw_word=word,
                condition=cond,
            )
        return Instruction(
            Mnemonic.CSINC,
            (
                RegisterOperand(rd, is_64bit),
                RegisterOperand(rn, is_64bit),
                RegisterOperand(rm, is_64bit),
            ),
            raw_word=word,
            condition=cond,
        )

    return None


# ============================================================
# Load/Store 解码
# ============================================================

def _try_decode_load_store(word: int) -> Instruction | None:
    # 立即数偏移格式: size(2) 111 0 V(0) 01 opc(2) imm12 Rn Rt
    # bits[29:27] = 111, bit[26] = 0, bits[25:24] = 01
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

    # 确定位宽
    if size == 0b11:
        is_64bit = True
        load = bool(opc & 1)
    elif size == 0b10:
        is_64bit = False
        load = bool(opc & 1)
    else:
        # 8/16 位暂不支持解码（可后续扩展）
        return None

    # 有符号加载 opc=10/11, 无符号 opc=00/01
    is_signed = bool(opc & 0b10)
    if is_signed and not load:
        return None  # 有符号 store 不合法

    base = RegisterOperand(rn, True)
    offset = imm12 << (size + (0 if size < 2 else 0))
    # 简化：imm12 * (1 << size)
    offset = sign_extend(imm12, 12) * (1 << size) if size < 2 else imm12 * (1 << size)
    mem_op = MemoryOperand(base, offset=offset)

    if load:
        return Instruction(
            Mnemonic.LDR,
            (RegisterOperand(rt, is_64bit), mem_op),
            raw_word=word,
        )
    return Instruction(
        Mnemonic.STR,
        (RegisterOperand(rt, is_64bit), mem_op),
        raw_word=word,
    )


# ============================================================
# 数据处理（寄存器）解码
# ============================================================

def _try_decode_data_processing_register(word: int) -> Instruction | None:
    # 数据处理（寄存器）: bits[28:24] = 01011
    if extract_bits(word, 24, 5) != 0b01011:
        return None

    sf = extract_bits(word, 31, 1)
    op = extract_bits(word, 30, 1)   # 0=逻辑, 1=算术
    s = extract_bits(word, 29, 1)
    opcode = extract_bits(word, 21, 4)  # bits[24:21]
    shift_type = extract_bits(word, 22, 2)
    rm = extract_bits(word, 16, 5)
    imm6 = extract_bits(word, 10, 6)
    rn = extract_bits(word, 5, 5)
    rd = extract_bits(word, 0, 5)
    is_64bit = bool(sf)

    rd_op = RegisterOperand(rd, is_64bit)
    rn_op = RegisterOperand(rn, is_64bit)
    rm_op = RegisterOperand(rm, is_64bit)

    # 带移位的第二操作数
    if imm6 == 0 and shift_type == 0:
        rm_shifted = rm_op
    else:
        rm_shifted = ShiftedOperand(rm_op, ShiftType.from_code(shift_type), imm6)

    # 算术指令 (op=1)
    if op == 1:
        # ADD/SUB (寄存器): opcode=01000, bit24=0
        if opcode == 0b0000:
            if s == 0:
                return Instruction(Mnemonic.ADD, (rd_op, rn_op, rm_shifted), raw_word=word)
            else:
                if rd == 31:
                    return Instruction(Mnemonic.CMN, (rn_op, rm_shifted), raw_word=word)
                return Instruction(Mnemonic.ADDS, (rd_op, rn_op, rm_shifted), raw_word=word)
        if opcode == 0b1000:
            if s == 0:
                return Instruction(Mnemonic.SUB, (rd_op, rn_op, rm_shifted), raw_word=word)
            else:
                if rd == 31:
                    return Instruction(Mnemonic.CMP, (rn_op, rm_shifted), raw_word=word)
                return Instruction(Mnemonic.SUBS, (rd_op, rn_op, rm_shifted), raw_word=word)
        # MUL: opcode=00111 (MADD with Ra=XZR)
        if opcode == 0b0011:
            return Instruction(Mnemonic.MUL, (rd_op, rn_op, rm_op), raw_word=word)
        # SDIV: opcode=00110, bit10=1
        if opcode == 0b0010:
            return Instruction(Mnemonic.SDIV, (rd_op, rn_op, rm_op), raw_word=word)
        # UDIV: opcode=00010, bit10=0
        if opcode == 0b0010 and s == 0:
            return Instruction(Mnemonic.UDIV, (rd_op, rn_op, rm_op), raw_word=word)

    # 逻辑指令 (op=0)
    if op == 0:
        if opcode == 0b0000:  # AND
            if s == 0:
                return Instruction(Mnemonic.AND, (rd_op, rn_op, rm_shifted), raw_word=word)
            else:
                return Instruction(Mnemonic.ANDS, (rd_op, rn_op, rm_shifted), raw_word=word)
        if opcode == 0b0001:  # ORR / BIC
            if s == 0:
                return Instruction(Mnemonic.ORR, (rd_op, rn_op, rm_shifted), raw_word=word)
        if opcode == 0b0010:  # ORN / EOR
            if s == 0:
                return Instruction(Mnemonic.EOR, (rd_op, rn_op, rm_shifted), raw_word=word)
        if opcode == 0b0100:  # EOR
            if s == 0:
                return Instruction(Mnemonic.EOR, (rd_op, rn_op, rm_shifted), raw_word=word)

    return None


# ============================================================
# HALT 伪指令解码
# ============================================================

# HALT 编码：使用一个 AArch64 未分配的编码区间
# bits[31:25] = 0000000, 全 0 视为 HALT（实际 ARM 中是 UDF #0）
HALT_ENCODING = 0x00000000


def _try_decode_halt(word: int) -> Instruction | None:
    if word == HALT_ENCODING:
        return Instruction(Mnemonic.HALT, (), raw_word=word)
    return None
