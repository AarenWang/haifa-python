"""AArch64 寄存器文件与 PSTATE 条件标志。

参照 ARM Architecture Reference Manual (ARMv8-A) 实现：
- 31 个 64 位通用寄存器 X0–X30
- XZR / WZR 零寄存器（读恒 0，写丢弃）
- SP（栈指针）、PC（程序计数器）
- PSTATE 条件标志 N / Z / C / V，按 ARM 规范计算
- W0–W30 是 X0–X30 的低 32 位视图（写 Wn 清高 32 位，读 Wn 零扩展）
"""

from __future__ import annotations

from dataclasses import dataclass

MASK64 = (1 << 64) - 1
MASK32 = (1 << 32) - 1


@dataclass
class PSTATE:
    """PSTATE 条件标志位。

    N — Negative：结果最高位为 1
    Z — Zero：结果为零
    C — Carry：加法进位 / 减法无借位
    V — oVerflow：有符号溢出
    """

    n: bool = False
    z: bool = False
    c: bool = False
    v: bool = False

    def reset(self) -> None:
        self.n = self.z = self.c = self.v = False

    def update_add(self, a: int, b: int, width: int = 64) -> None:
        """按 ARM 规范更新标志位，对应 ADDS (a + b)。"""
        mask = (1 << width) - 1
        sign_bit = 1 << (width - 1)
        a_u = a & mask
        b_u = b & mask
        full = a_u + b_u
        result = full & mask
        self.n = bool(result & sign_bit)
        self.z = result == 0
        self.c = full > mask
        # 有符号溢出：两操作数同号，结果异号
        self.v = bool(((a_u ^ result) & (b_u ^ result)) & sign_bit)

    def update_sub(self, a: int, b: int, width: int = 64) -> None:
        """按 ARM 规范更新标志位，对应 SUBS (a - b)。

        ARM 中减法通过 a + (~b) + 1 实现，因此：
        C = NOT borrow = a >= b（无符号）
        V = 有符号溢出：两操作数异号，结果与 a 异号
        """
        mask = (1 << width) - 1
        sign_bit = 1 << (width - 1)
        a_u = a & mask
        b_u = b & mask
        result = (a_u - b_u) & mask
        self.n = bool(result & sign_bit)
        self.z = result == 0
        self.c = a_u >= b_u
        self.v = bool(((a_u ^ b_u) & (a_u ^ result)) & sign_bit)

    def update_logical(self, result: int, width: int = 64, carry: bool | None = None) -> None:
        """更新标志位，对应 ANDS / ORRS / EORS 等逻辑运算。

        对于逻辑运算，C 和 V 通常清零，除非来自移位立即数（此处简化）。
        """
        mask = (1 << width) - 1
        sign_bit = 1 << (width - 1)
        result_u = result & mask
        self.n = bool(result_u & sign_bit)
        self.z = result_u == 0
        self.c = bool(carry) if carry is not None else False
        self.v = False

    def condition_holds(self, cond: str) -> bool:
        """判断条件码 cond 是否成立。

        覆盖 AArch64 全部 16 种条件：
        EQ NE CS HS CC LO MI PL VS VC HI LS GE LT GT LE AL NV
        """
        cond = cond.upper()
        n, z, c, v = self.n, self.z, self.c, self.v
        table = {
            "EQ": z,
            "NE": not z,
            "CS": c,        # 同 HS
            "HS": c,
            "CC": not c,    # 同 LO
            "LO": not c,
            "MI": n,
            "PL": not n,
            "VS": v,
            "VC": not v,
            "HI": c and not z,
            "LS": not c or z,
            "GE": n == v,
            "LT": n != v,
            "GT": not z and n == v,
            "LE": z or n != v,
            "AL": True,
            "NV": False,
        }
        if cond not in table:
            raise ValueError(f"unknown condition: {cond}")
        return table[cond]

    def to_dict(self) -> dict[str, bool]:
        return {"N": self.n, "Z": self.z, "C": self.c, "V": self.v}


class RegisterFile:
    """AArch64 寄存器文件。

    - X0–X30：31 个 64 位通用寄存器，索引 0–30
    - 索引 31：XZR / WZR 零寄存器（读返回 0，写丢弃）
    - SP、PC：独立的 64 位寄存器
    - PSTATE：条件标志
    - LR 是 X30 的别名
    """

    NUM_REGISTERS = 31  # X0–X30

    def __init__(self) -> None:
        self._regs: list[int] = [0] * self.NUM_REGISTERS
        self.sp: int = 0
        self.pc: int = 0
        self.pstate = PSTATE()

    # ---- 64 位读写 (X 寄存器) ----

    def read_x(self, index: int) -> int:
        """读取 64 位寄存器值。索引 31 = XZR，返回 0。"""
        if index == 31:
            return 0
        return self._regs[index] & MASK64

    def write_x(self, index: int, value: int) -> None:
        """写入 64 位寄存器。索引 31 = XZR，丢弃写入。"""
        if index == 31:
            return
        self._regs[index] = value & MASK64

    # ---- 32 位读写 (W 寄存器视图) ----

    def read_w(self, index: int) -> int:
        """读取低 32 位（零扩展到 64 位）。索引 31 = WZR，返回 0。"""
        if index == 31:
            return 0
        return self._regs[index] & MASK32

    def write_w(self, index: int, value: int) -> None:
        """写入低 32 位并清除高 32 位。索引 31 = WZR，丢弃写入。"""
        if index == 31:
            return
        self._regs[index] = value & MASK32

    # ---- SP / PC ----

    def read_sp(self) -> int:
        return self.sp & MASK64

    def write_sp(self, value: int) -> None:
        self.sp = value & MASK64

    def read_pc(self) -> int:
        return self.pc & MASK64

    def write_pc(self, value: int) -> None:
        self.pc = value & MASK64

    # ---- 名称解析 ----

    @staticmethod
    def parse_name(name: str) -> tuple[str, int]:
        """解析寄存器名称，返回 (类型, 索引)。

        支持的名称：X0–X30, W0–W30, XZR, WZR, SP, PC, LR(=X30), FP(=X29)

        返回类型：
        - 'X'：64 位通用寄存器，索引 0–30 或 31(XZR)
        - 'W'：32 位通用寄存器，索引 0–30 或 31(WZR)
        - 'SP'：栈指针
        - 'PC'：程序计数器
        """
        name = name.strip().upper()
        if name == "SP":
            return ("SP", 0)
        if name == "PC":
            return ("PC", 0)
        if name == "XZR":
            return ("X", 31)
        if name == "WZR":
            return ("W", 31)
        if name == "LR":
            return ("X", 30)
        if name == "FP":
            return ("X", 29)
        if name.startswith("X") and name[1:].isdigit():
            idx = int(name[1:])
            if 0 <= idx <= 30:
                return ("X", idx)
        if name.startswith("W") and name[1:].isdigit():
            idx = int(name[1:])
            if 0 <= idx <= 30:
                return ("W", idx)
        raise ValueError(f"unknown register name: {name!r}")

    def read_by_name(self, name: str) -> int:
        """按名称读取寄存器值。X 返回 64 位，W 返回 32 位零扩展。"""
        kind, index = self.parse_name(name)
        if kind == "X":
            return self.read_x(index)
        if kind == "W":
            return self.read_w(index)
        if kind == "SP":
            return self.read_sp()
        if kind == "PC":
            return self.read_pc()
        raise ValueError(f"cannot read register: {name!r}")

    def write_by_name(self, name: str, value: int) -> None:
        """按名称写入寄存器。X 写 64 位，W 写 32 位（清高 32 位）。"""
        kind, index = self.parse_name(name)
        if kind == "X":
            self.write_x(index, value)
        elif kind == "W":
            self.write_w(index, value)
        elif kind == "SP":
            self.write_sp(value)
        elif kind == "PC":
            self.write_pc(value)
        else:
            raise ValueError(f"cannot write register: {name!r}")

    # ---- 快照 ----

    def snapshot(self) -> dict[str, object]:
        """返回可读的寄存器快照，用于调试与可视化。"""
        regs = {f"X{i}": self._regs[i] for i in range(self.NUM_REGISTERS)}
        regs["SP"] = self.sp
        regs["PC"] = self.pc
        return {
            "registers": regs,
            "pstate": self.pstate.to_dict(),
        }
