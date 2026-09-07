"""AArch64 执行引擎。

实现 fetch-decode-execute 循环：
1. fetch：从 PC 地址读取 4 字节
2. decode：调用 decoder 解析指令
3. execute：执行对应操作，更新寄存器与标志位
4. update PC：默认 PC += 4，分支指令修改 PC

支持单步执行、连续运行、执行日志。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .decoder import DecodeError, decode
from .instructions import (
    Condition,
    ImmediateOperand,
    Instruction,
    LabelOperand,
    MemoryOperand,
    Mnemonic,
    RegisterOperand,
    ShiftedOperand,
    ShiftType,
)
from .memory import Memory
from .registers import RegisterFile, MASK64, MASK32


class ExecutionError(Exception):
    """执行错误。"""


@dataclass
class ExecutionStep:
    """单步执行记录，用于执行日志。"""
    pc: int
    word: int
    instruction: Instruction
    description: str = ""


class Executor:
    """AArch64 执行引擎。

    Attributes:
        regs: 寄存器文件
        memory: 统一字节寻址内存
        halted: 是否已停机
        trace: 执行日志（启用时记录每步）
        trace_enabled: 是否启用执行日志
    """

    def __init__(
        self,
        regs: RegisterFile | None = None,
        memory: Memory | None = None,
        *,
        trace_enabled: bool = False,
    ) -> None:
        self.regs = regs or RegisterFile()
        self.memory = memory or Memory(65536)
        self.halted = False
        self.trace_enabled = trace_enabled
        self.trace: list[ExecutionStep] = []
        self._output: list[Any] = []
        # MMIO 地址：写入即打印
        self.mmio_output_addr = 0x0900_0000

    @classmethod
    def from_words(
        cls,
        words: list[int],
        *,
        base_addr: int = 0,
        memory_size: int = 65536,
        sp: int | None = None,
        trace_enabled: bool = False,
    ) -> "Executor":
        """从 32 位字列表创建执行器，程序加载到 base_addr。"""
        # 预留栈空间（栈从内存末尾向下增长），确保 SP 及 [SP] 均可寻址
        stack_headroom = 4096
        # 保证 SP 从内存末尾向下，且 sp+8 仍在边界内
        need = base_addr + len(words) * 4 + 1024
        mem_size = max(memory_size, need)
        total = mem_size + stack_headroom
        mem = Memory(total)
        for i, word in enumerate(words):
            mem.write_u32(base_addr + i * 4, word & 0xFFFFFFFF)
        regs = RegisterFile()
        regs.write_pc(base_addr)
        # SP 默认指向堆栈区域顶部（即 pre-stack_headroom 偏移），栈向下增长。
        regs.write_sp(sp if sp is not None else mem_size)
        return cls(regs, mem, trace_enabled=trace_enabled)

    @classmethod
    def from_assemble_result(
        cls,
        result: Any,
        *,
        memory_size: int = 65536,
        sp: int | None = None,
        trace_enabled: bool = False,
    ) -> "Executor":
        """从汇编结果创建执行器。"""
        return cls.from_words(
            result.words,
            base_addr=result.base_addr,
            memory_size=memory_size,
            sp=sp,
            trace_enabled=trace_enabled,
        )

    # ============================================================
    # 执行控制
    # ============================================================

    def run(self, *, max_steps: int = 100000) -> list[Any]:
        """连续执行直到停机或达到步数上限。"""
        steps = 0
        while steps < max_steps:
            if self.halted:
                break
            self.step()
            steps += 1
        if not self.halted:
            if steps >= max_steps:
                raise ExecutionError(f"maximum step count exceeded: {max_steps}")
        return list(self._output)

    def step(self) -> bool:
        """执行单步。返回 False 表示已停机。"""
        if self.halted:
            return False

        pc = self.regs.read_pc()

        # Fetch
        try:
            word = self.memory.read_word(pc)
        except Exception as exc:
            raise ExecutionError(f"fetch failed at PC=0x{pc:08x}: {exc}") from exc

        # Decode
        try:
            inst = decode(word)
        except DecodeError as exc:
            raise ExecutionError(f"decode failed at PC=0x{pc:08x}: {exc}") from exc

        # Execute
        old_pc = pc
        self._pc_explicitly_set = False
        desc = self._execute(inst, word)

        # Update PC (if not already modified by branch)
        if not self._pc_explicitly_set and not self.halted:
            self.regs.write_pc(old_pc + 4)

        # Trace
        if self.trace_enabled:
            self.trace.append(ExecutionStep(pc=old_pc, word=word, instruction=inst, description=desc))

        return not self.halted

    # ============================================================
    # 指令执行
    # ============================================================

    def _execute(self, inst: Instruction, raw_word: int = 0) -> str:
        """执行指令，返回描述字符串。"""
        mn = inst.mnemonic
        ops = inst.operands

        if mn == Mnemonic.HALT:
            self.halted = True
            return "HALT"

        if mn == Mnemonic.NOP:
            return "NOP"

        if mn == Mnemonic.MOVZ:
            return self._exec_movz(ops, inst.raw_word or raw_word)
        if mn == Mnemonic.MOVN:
            return self._exec_movn(ops, inst.raw_word or raw_word)
        if mn == Mnemonic.MOVK:
            return self._exec_movk(ops, inst.raw_word or raw_word)

        if mn == Mnemonic.ADD:
            return self._exec_add_sub(ops, is_sub=False, set_flags=False)
        if mn == Mnemonic.ADDS:
            return self._exec_add_sub(ops, is_sub=False, set_flags=True)
        if mn == Mnemonic.SUB:
            return self._exec_add_sub(ops, is_sub=True, set_flags=False)
        if mn == Mnemonic.SUBS:
            return self._exec_add_sub(ops, is_sub=True, set_flags=True)
        if mn == Mnemonic.CMP:
            return self._exec_cmp_cmn(ops, is_sub=True)
        if mn == Mnemonic.CMN:
            return self._exec_cmp_cmn(ops, is_sub=False)

        if mn == Mnemonic.MUL:
            return self._exec_mul(ops)
        if mn == Mnemonic.SDIV:
            return self._exec_div(ops, signed=True)
        if mn == Mnemonic.UDIV:
            return self._exec_div(ops, signed=False)

        if mn == Mnemonic.MOV:
            return self._exec_mov(ops)
        if mn == Mnemonic.MVN:
            return self._exec_mvn(ops)
        if mn == Mnemonic.AND:
            return self._exec_logical(ops, op="and", set_flags=False)
        if mn == Mnemonic.ANDS:
            return self._exec_logical(ops, op="and", set_flags=True)
        if mn == Mnemonic.ORR:
            return self._exec_logical(ops, op="or", set_flags=False)
        if mn == Mnemonic.EOR:
            return self._exec_logical(ops, op="xor", set_flags=False)

        if mn == Mnemonic.LSL:
            return self._exec_shift(ops, ShiftType.LSL)
        if mn == Mnemonic.LSR:
            return self._exec_shift(ops, ShiftType.LSR)
        if mn == Mnemonic.ASR:
            return self._exec_shift(ops, ShiftType.ASR)
        if mn == Mnemonic.ROR:
            return self._exec_shift(ops, ShiftType.ROR)

        if mn == Mnemonic.CSEL:
            return self._exec_csel(ops, inst.condition)
        if mn == Mnemonic.CSET:
            return self._exec_cset(ops, inst.condition)
        if mn == Mnemonic.CSINC:
            return self._exec_csinc(ops, inst.condition)

        if mn == Mnemonic.B:
            return self._exec_branch(ops)
        if mn == Mnemonic.BL:
            return self._exec_bl(ops)
        if mn == Mnemonic.BR:
            return self._exec_br(ops)
        if mn == Mnemonic.BLR:
            return self._exec_blr(ops)
        if mn == Mnemonic.RET:
            return self._exec_ret(ops)
        if mn == Mnemonic.B_COND:
            return self._exec_b_cond(ops, inst.condition)

        if mn == Mnemonic.LDR:
            return self._exec_ldr(ops)
        if mn == Mnemonic.STR:
            return self._exec_str(ops)

        raise ExecutionError(f"unimplemented instruction: {mn}")

    # --- MOVZ/MOVN/MOVK ---

    def _exec_movz(self, ops, raw_word: int = 0) -> str:
        rd = ops[0]
        imm = ops[1].value
        hw = self._extract_hw(raw_word)
        value = imm << (hw * 16)
        self._write_reg(rd, value)
        return f"{rd} = 0x{value:x}"

    def _exec_movn(self, ops, raw_word: int = 0) -> str:
        rd = ops[0]
        imm = ops[1].value
        hw = self._extract_hw(raw_word)
        value = (~(imm << (hw * 16))) & MASK64
        self._write_reg(rd, value)
        return f"{rd} = 0x{self._read_reg(rd):x}"

    def _exec_movk(self, ops, raw_word: int = 0) -> str:
        rd = ops[0]
        imm = ops[1].value
        hw = self._extract_hw(raw_word)
        old = self._read_reg(rd)
        mask = 0xFFFF << (hw * 16)
        value = (old & ~mask) | ((imm << (hw * 16)) & mask)
        self._write_reg(rd, value)
        return f"{rd} = 0x{value:x}"

    def _extract_hw(self, raw_word: int = 0) -> int:
        """从 raw 32 位指令字中提取 MOVZ/MOVN/MOVK 的 hw（移位量/16）。

        AArch64 mov wide 格式：hw 位于 bits[22:21]。
        """
        if not raw_word:
            return 0
        return (raw_word >> 21) & 0x3

    # --- ADD/SUB ---

    def _exec_add_sub(self, ops, *, is_sub: bool, set_flags: bool) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_operand_value(ops[2])
        if is_sub:
            result = (rn_val - rm_val) & MASK64
            if set_flags:
                self.regs.pstate.update_sub(rn_val, rm_val, width=64)
        else:
            result = (rn_val + rm_val) & MASK64
            if set_flags:
                self.regs.pstate.update_add(rn_val, rm_val, width=64)
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    def _exec_cmp_cmn(self, ops, *, is_sub: bool) -> str:
        rn_val = self._read_reg(ops[0])
        rm_val = self._read_operand_value(ops[1])
        if is_sub:
            self.regs.pstate.update_sub(rn_val, rm_val, width=64)
        else:
            self.regs.pstate.update_add(rn_val, rm_val, width=64)
        return f"NZCV = {self.regs.pstate.to_dict()}"

    # --- MUL/DIV ---

    def _exec_mul(self, ops) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_reg(ops[2])
        result = (rn_val * rm_val) & MASK64
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    def _exec_div(self, ops, *, signed: bool) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_reg(ops[2])
        if rm_val == 0:
            result = 0
        elif signed:
            rn_signed = rn_val - (1 << 64) if rn_val & (1 << 63) else rn_val
            rm_signed = rm_val - (1 << 64) if rm_val & (1 << 63) else rm_val
            if rm_signed == 0:
                result = 0
            else:
                q = rn_signed // rm_signed
                result = q & MASK64
        else:
            result = (rn_val // rm_val) & MASK64
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    # --- MOV/MVN/逻辑 ---

    def _exec_mov(self, ops) -> str:
        rd = ops[0]
        rm_val = self._read_reg(ops[1])
        self._write_reg(rd, rm_val)
        return f"{rd} = 0x{rm_val:x}"

    def _exec_mvn(self, ops) -> str:
        rd = ops[0]
        rm_val = self._read_reg(ops[1])
        result = (~rm_val) & MASK64
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    def _exec_logical(self, ops, *, op: str, set_flags: bool) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_operand_value(ops[2])
        if op == "and":
            result = rn_val & rm_val
        elif op == "or":
            result = rn_val | rm_val
        elif op == "xor":
            result = rn_val ^ rm_val
        else:
            raise ExecutionError(f"unknown logical op: {op}")
        result &= MASK64
        self._write_reg(rd, result)
        if set_flags:
            self.regs.pstate.update_logical(result, width=64)
        return f"{rd} = 0x{result:x}"

    # --- 移位 ---

    def _exec_shift(self, ops, shift_type: ShiftType) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_reg(ops[2])
        shift_amount = rm_val & 0x3F
        if shift_type == ShiftType.LSL:
            result = (rn_val << shift_amount) & MASK64
        elif shift_type == ShiftType.LSR:
            result = (rn_val >> shift_amount) & MASK64 if shift_amount < 64 else 0
        elif shift_type == ShiftType.ASR:
            rn_signed = rn_val - (1 << 64) if rn_val & (1 << 63) else rn_val
            result = (rn_signed >> shift_amount) & MASK64 if shift_amount < 64 else (MASK64 if rn_signed < 0 else 0)
        elif shift_type == ShiftType.ROR:
            shift_amount = shift_amount & 0x3F
            result = ((rn_val >> shift_amount) | (rn_val << (64 - shift_amount))) & MASK64 if shift_amount else rn_val
        else:
            raise ExecutionError(f"unknown shift type: {shift_type}")
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    # --- 条件选择 ---

    def _exec_csel(self, ops, condition: Condition | None) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_reg(ops[2])
        cond = condition or Condition.AL
        result = rn_val if self.regs.pstate.condition_holds(cond.name_str) else rm_val
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    def _exec_cset(self, ops, condition: Condition | None) -> str:
        rd = ops[0]
        cond = condition or Condition.AL
        result = 1 if self.regs.pstate.condition_holds(cond.name_str) else 0
        self._write_reg(rd, result)
        return f"{rd} = {result}"

    def _exec_csinc(self, ops, condition: Condition | None) -> str:
        rd = ops[0]
        rn_val = self._read_reg(ops[1])
        rm_val = self._read_reg(ops[2])
        cond = condition or Condition.AL
        result = rn_val if self.regs.pstate.condition_holds(cond.name_str) else (rm_val + 1) & MASK64
        self._write_reg(rd, result)
        return f"{rd} = 0x{result:x}"

    # --- 分支 ---

    def _exec_branch(self, ops) -> str:
        target = self._resolve_branch_target(ops[0])
        self.regs.write_pc(target)
        self._pc_explicitly_set = True
        return f"-> 0x{target:08x}"

    def _exec_bl(self, ops) -> str:
        pc = self.regs.read_pc()
        target = self._resolve_branch_target(ops[0])
        self.regs.write_x(30, pc + 4)  # LR = return address
        self.regs.write_pc(target)
        self._pc_explicitly_set = True
        return f"LR=0x{pc + 4:08x}, -> 0x{target:08x}"

    def _exec_br(self, ops) -> str:
        target = self._read_reg(ops[0])
        self.regs.write_pc(target)
        self._pc_explicitly_set = True
        return f"-> 0x{target:08x}"

    def _exec_blr(self, ops) -> str:
        pc = self.regs.read_pc()
        target = self._read_reg(ops[0])
        self.regs.write_x(30, pc + 4)
        self.regs.write_pc(target)
        self._pc_explicitly_set = True
        return f"LR=0x{pc + 4:08x}, -> 0x{target:08x}"

    def _exec_ret(self, ops) -> str:
        if ops:
            target = self._read_reg(ops[0])
        else:
            target = self.regs.read_x(30)  # default LR
        self.regs.write_pc(target)
        self._pc_explicitly_set = True
        return f"-> 0x{target:08x}"

    def _exec_b_cond(self, ops, condition: Condition | None) -> str:
        cond = condition or Condition.AL
        pc = self.regs.read_pc()
        target = self._resolve_branch_target(ops[0])
        if self.regs.pstate.condition_holds(cond.name_str):
            self.regs.write_pc(target)
            self._pc_explicitly_set = True
            return f"{cond.name_str} taken -> 0x{target:08x}"
        return f"{cond.name_str} not taken"

    def _resolve_branch_target(self, operand) -> int:
        """解析分支目标。LabelOperand 含 offset，其他尝试立即数。"""
        if isinstance(operand, LabelOperand):
            pc = self.regs.read_pc()
            return (pc + operand.offset) & MASK64
        if isinstance(operand, ImmediateOperand):
            return operand.value & MASK64
        raise ExecutionError(f"cannot resolve branch target: {operand}")

    # --- Load/Store ---

    def _exec_ldr(self, ops) -> str:
        rt = ops[0]
        mem_op = ops[1]
        addr = self._resolve_address(mem_op)
        value = self.memory.read_u64(addr)
        self._write_reg(rt, value)
        self._apply_writeback(mem_op, addr)
        return f"{rt} = [0x{addr:08x}] = 0x{value:x}"

    def _exec_str(self, ops) -> str:
        rt = ops[0]
        mem_op = ops[1]
        addr = self._resolve_address(mem_op)
        value = self._read_reg(rt)
        self.memory.write_u64(addr, value)
        self._apply_writeback(mem_op, addr)
        return f"[0x{addr:08x}] = {rt} = 0x{value:x}"

    def _resolve_address(self, mem_op: MemoryOperand) -> int:
        # load/store 中寄存器编号 31 表示 SP，而非 XZR（XZR 用于数据处理）
        if mem_op.base.index == 31:
            base = self.regs.read_sp()
        else:
            base = self._read_reg(mem_op.base)
        # post-indexed: 地址 = base（offset 仅用于写回）
        if mem_op.post_indexed:
            return base & MASK64
        # offset/pre-indexed: 地址 = base + offset
        return (base + mem_op.offset) & MASK64

    def _apply_writeback(self, mem_op: MemoryOperand, addr: int) -> None:
        """应用前索引/后索引的基址写回。"""
        if mem_op.pre_indexed or mem_op.post_indexed:
            if mem_op.base.index == 31:
                self.regs.write_sp((self.regs.read_sp() + mem_op.offset) & MASK64)
            else:
                self._write_reg(mem_op.base, (self._read_reg(mem_op.base) + mem_op.offset) & MASK64)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _read_reg(self, operand) -> int:
        """从 RegisterOperand 读取值。"""
        if isinstance(operand, RegisterOperand):
            if operand.is_64bit:
                return self.regs.read_x(operand.index)
            return self.regs.read_w(operand.index)
        raise ExecutionError(f"expected register operand, got {operand}")

    def _write_reg(self, operand, value: int) -> None:
        """写入 RegisterOperand。"""
        if isinstance(operand, RegisterOperand):
            if operand.is_64bit:
                self.regs.write_x(operand.index, value)
            else:
                self.regs.write_w(operand.index, value)
        else:
            raise ExecutionError(f"expected register operand, got {operand}")

    def _read_operand_value(self, operand) -> int:
        """读取操作数值：寄存器或立即数。"""
        if isinstance(operand, RegisterOperand):
            return self._read_reg(operand)
        if isinstance(operand, ImmediateOperand):
            return operand.value
        if isinstance(operand, ShiftedOperand):
            base = self._read_reg(operand.register)
            amount = operand.shift_amount
            if operand.shift_type == ShiftType.LSL:
                return (base << amount) & MASK64
            if operand.shift_type == ShiftType.LSR:
                return (base >> amount) & MASK64 if amount < 64 else 0
            if operand.shift_type == ShiftType.ASR:
                signed = base - (1 << 64) if base & (1 << 63) else base
                return (signed >> amount) & MASK64 if amount < 64 else (MASK64 if signed < 0 else 0)
            if operand.shift_type == ShiftType.ROR:
                amount = amount & 0x3F
                return ((base >> amount) | (base << (64 - amount))) & MASK64 if amount else base
        raise ExecutionError(f"cannot read operand value: {operand}")

    # ============================================================
    # 快照
    # ============================================================

    def snapshot(self) -> dict[str, Any]:
        """返回执行器状态快照。"""
        return {
            "halted": self.halted,
            "registers": self.regs.snapshot()["registers"],
            "pstate": self.regs.pstate.to_dict(),
            "pc": self.regs.read_pc(),
            "output": list(self._output),
            "trace_count": len(self.trace),
        }
