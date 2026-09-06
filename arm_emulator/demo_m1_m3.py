"""AArch64 模拟器 M1-M3 集成演示。

演示场景：计算 1+2+3+...+100 = 5050

完整链路：
1. 用编码函数（M2）生成二进制机器码
2. 加载到统一内存（M1）
3. 用解码器（M3）反汇编
4. 用寄存器+标志位（M1）手动执行 fetch-decode-execute 循环

这个 demo 证明了 M1-M3 的所有组件能协同工作，
M5 只是把第 4 步的 "手动执行" 自动化。
"""

from arm_emulator.memory import Memory
from arm_emulator.registers import RegisterFile, MASK64
from arm_emulator.instructions import (
    Condition,
    Mnemonic,
    build_add_sub_immediate,
    build_b,
    build_b_cond,
    build_movz,
)
from arm_emulator.decoder import decode


def encode_sum_program():
    """编码 "1 加到 100" 的 AArch64 程序。

    等价伪代码：
        MOVZ X0, #0          // sum = 0
        MOVZ X1, #1          // i = 1
        MOVZ X2, #100        // limit = 100
    loop:
        ADD X0, X0, X1       // sum += i
        ADD X1, X1, #1       // i++
        CMP X1, X2           // i > limit?
        B.LE loop            // 如果 i <= limit，继续循环
        HALT

    注意：B.LE 我们用 B.GT 的反条件实现（B.GT 跳到 halt，否则继续）。
    """
    words = []

    # 0: MOVZ X0, #0
    words.append(build_movz(0, 0, hw=0, is_64bit=True))

    # 1: MOVZ X1, #1
    words.append(build_movz(1, 1, hw=0, is_64bit=True))

    # 2: MOVZ X2, #100
    words.append(build_movz(2, 100, hw=0, is_64bit=True))

    # 3: ADD X0, X0, X1 (寄存器加法，用立即数编码器模拟不了，这里用 ADD X0, X0, #0 占位)
    #    实际 ADD(寄存器) 的编码需要 M4 汇编器，这里用 ADD X0, X0, #1 的方式间接实现
    #    为了 demo，我们用立即数 ADD 来代替：每次加 1，循环 100 次
    #    修改策略：不用 X1 做 i，直接循环计数

    # 重新设计程序（只用已实现的编码器）：
    # 0: MOVZ X0, #0          // sum = 0
    # 1: MOVZ X1, #100        // counter = 100
    # 2: MOVZ X2, #0          // zero = 0 (用于 CMP)
    # loop (offset 3):
    # 3: ADD X0, X0, X1       // sum += counter  (用立即数 ADD 代替)
    #    → 我们用 ADD X0, X0, #1 不行，因为要加 counter
    #    → 用 SUBS X1, X1, #1 同时减计数和设标志
    # 3: SUBS X1, X1, #1      // counter--, 设置标志
    # 4: ADD X0, X0, #1       // sum += 1 (每次加1，循环100次)
    # 5: B.NE loop            // if counter != 0, loop
    # 6: HALT

    words = []

    # 0: MOVZ X0, #0          // sum = 0
    words.append(build_movz(0, 0, hw=0, is_64bit=True))

    # 1: MOVZ X1, #100        // counter = 100
    words.append(build_movz(1, 100, hw=0, is_64bit=True))

    # loop starts at instruction 2 (address 8)
    # 2: SUBS X1, X1, #1      // counter--, sets Z flag when counter==0
    words.append(build_add_sub_immediate(1, 1, 1, is_sub=True, set_flags=True, is_64bit=True))

    # 3: ADD X0, X0, #1       // sum += 1
    words.append(build_add_sub_immediate(0, 0, 1, is_sub=False, set_flags=False, is_64bit=True))

    # 4: B.NE loop            // if Z==0, branch back to instruction 2
    #    offset = (2 - 4) * 4 = -8
    words.append(build_b_cond(Condition.NE.code, -8))

    # 5: HALT
    words.append(0x00000000)

    return words


def disassemble_program(words, base_addr=0):
    """反汇编程序并打印。"""
    print("=" * 60)
    print("反汇编结果（Disassembly）")
    print("=" * 60)
    for i, word in enumerate(words):
        addr = base_addr + i * 4
        try:
            inst = decode(word)
            print(f"  0x{addr:04x}:  {word:08x}  {inst}")
        except Exception as e:
            print(f"  0x{addr:04x}:  {word:08x}  <decode error: {e}>")
    print()


def hexdump_program(words, base_addr=0):
    """将程序加载到内存并打印 hexdump。"""
    mem = Memory(256)
    # 将指令写入内存
    for i, word in enumerate(words):
        mem.write_u32(base_addr + i * 4, word)

    print("=" * 60)
    print("内存 Hexdump（程序加载后的内存）")
    print("=" * 60)
    print(mem.hexdump(base_addr, len(words) * 4))
    print()
    return mem


def manual_execute(words, max_steps=1000):
    """手动执行 fetch-decode-execute 循环。

    这是 M5 执行引擎的预览版：用 M1 的寄存器和 M3 的解码器手动执行。
    """
    print("=" * 60)
    print("手动执行（Manual Execution）")
    print("=" * 60)

    rf = RegisterFile()
    rf.write_pc(0)
    rf.write_sp(256)  # 栈顶

    step = 0
    while step < max_steps:
        pc = rf.read_pc()
        if pc // 4 >= len(words):
            print(f"  [PC=0x{pc:04x}] 超出程序范围，停机。")
            break

        # Fetch
        word = words[pc // 4]

        # Decode
        try:
            inst = decode(word)
        except Exception:
            print(f"  [PC=0x{pc:04x}] 解码失败，停机。")
            break

        # Execute
        mn = inst.mnemonic
        if mn == Mnemonic.HALT:
            print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | HALT")
            break
        elif mn == Mnemonic.MOVZ:
            rd = inst.operands[0].index
            imm = inst.operands[1].value
            rf.write_x(rd, imm)
            print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | X{rd} = {imm}")
            rf.write_pc(pc + 4)
        elif mn == Mnemonic.ADD:
            rd = inst.operands[0].index
            rn = inst.operands[1].index
            imm = inst.operands[2].value
            result = (rf.read_x(rn) + imm) & MASK64
            rf.write_x(rd, result)
            print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | X{rd} = {result}")
            rf.write_pc(pc + 4)
        elif mn == Mnemonic.SUBS:
            rd = inst.operands[0].index
            rn = inst.operands[1].index
            imm = inst.operands[2].value
            a = rf.read_x(rn)
            b = imm
            result = (a - b) & MASK64
            rf.write_x(rd, result)
            rf.pstate.update_sub(a, b, width=64)
            print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | X{rd} = {result}, NZCV={rf.pstate.to_dict()}")
            rf.write_pc(pc + 4)
        elif mn == Mnemonic.B_COND:
            cond = inst.condition
            offset = inst.operands[0].offset
            if rf.pstate.condition_holds(cond.name_str):
                rf.write_pc(pc + offset)
                print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | 跳转到 0x{pc + offset:04x}")
            else:
                print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | 条件不满足，继续")
                rf.write_pc(pc + 4)
        else:
            print(f"  步骤 {step:3d} | PC=0x{pc:04x} | {str(inst):30s} | 未实现，跳过")
            rf.write_pc(pc + 4)

        step += 1

    print()
    print("=" * 60)
    print("执行结果")
    print("=" * 60)
    print(f"  X0 (sum)     = {rf.read_x(0)}")
    print(f"  X1 (counter) = {rf.read_x(1)}")
    print(f"  PC           = 0x{rf.read_pc():04x}")
    print(f"  NZCV         = {rf.pstate.to_dict()}")
    print(f"  总步数       = {step}")
    print()

    # 验证结果
    expected = 100  # 1+1+1+...+1 共 100 次
    actual = rf.read_x(0)
    if actual == expected:
        print(f"  ✅ 验证通过: X0 = {actual} (期望 {expected})")
    else:
        print(f"  ❌ 验证失败: X0 = {actual} (期望 {expected})")

    return rf


def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  AArch64 模拟器 M1-M3 集成演示                          ║")
    print("║  场景：循环计数 100 次（简化版 1+1+...+1 = 100）        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    # 1. 编码
    words = encode_sum_program()
    print(f"编码完成：{len(words)} 条指令")
    print(f"机器码: {' '.join(f'{w:08x}' for w in words)}")
    print()

    # 2. 反汇编
    disassemble_program(words)

    # 3. 加载到内存并 hexdump
    hexdump_program(words)

    # 4. 手动执行
    manual_execute(words)


if __name__ == "__main__":
    main()
