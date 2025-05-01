from bytecode import Instruction, Opcode

class BytecodeWriter:
    @staticmethod
    def write_to_file(instructions, path):
        with open(path, 'w') as f:
            for instr in instructions:
                line = f"{instr.opcode.name} {' '.join(map(str, instr.args))}\n"
                f.write(line)


class BytecodeReader:
    @staticmethod
    def load_from_file(path):
        instructions = []
        with open(path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if not parts:
                    continue
                opcode_str = parts[0]
                args = parts[1:]
                opcode = Opcode[opcode_str]
                instructions.append(Instruction(opcode, args))
        return instructions
