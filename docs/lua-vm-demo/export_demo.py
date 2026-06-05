from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import asdict, is_dataclass
from typing import Any


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from compiler.bytecode_vm import BytecodeVM, Cell  # noqa: E402
from compiler.vm_errors import VMRuntimeError  # noqa: E402
from haifa_lua.environment import BuiltinFunction  # noqa: E402
from haifa_lua.runtime import compile_source  # noqa: E402
from haifa_lua.stdlib import create_default_environment  # noqa: E402
from haifa_lua.table import LuaTable  # noqa: E402


DEMOS = [
    {
        "id": "factorial",
        "title": "Recursive Factorial",
        "summary": "Function definition, recursive CALL_VALUE, RETURN, and arithmetic.",
        "focus": ["function call", "recursion", "return value"],
        "source_name": "factorial.lua",
        "source": """function fact(n)
  if n == 0 then
    return 1
  end
  return n * fact(n - 1)
end

return fact(5)
""",
    },
    {
        "id": "closure-counter",
        "title": "Closure Counter",
        "summary": "A nested function captures x through a VM cell and mutates it.",
        "focus": ["closure", "upvalue", "MAKE_CELL", "CELL_GET", "CELL_SET"],
        "source_name": "closure_counter.lua",
        "source": """function make_counter()
  local x = 0
  return function()
    x = x + 1
    return x
  end
end

local c = make_counter()
return c(), c(), c()
""",
    },
    {
        "id": "table-loop",
        "title": "Table Loop",
        "summary": "A table constructor plus numeric for loop reads values and accumulates a sum.",
        "focus": ["table", "numeric for", "LEN", "TABLE_GET", "ADD"],
        "source_name": "table_loop.lua",
        "source": """local values = {1, 2, 3, 4, 5}
local sum = 0

for i = 1, #values do
  sum = sum + values[i]
end

return sum
""",
    },
]


OPCODE_EXPLANATIONS = {
    "LOAD_IMM": "Put a small immediate number into a register.",
    "LOAD_CONST": "Put a constant value such as nil, string, or boolean into a register.",
    "MOV": "Copy a value from one register to another.",
    "ADD": "Add two values and store the result.",
    "SUB": "Subtract the right value from the left value.",
    "MUL": "Multiply two values.",
    "DIV": "Divide two values.",
    "EQ": "Compare two values for equality.",
    "GT": "Check whether the left value is greater than the right value.",
    "LT": "Check whether the left value is less than the right value.",
    "NOT": "Compute Lua logical not.",
    "LEN": "Compute Lua length, often used for table length.",
    "JZ": "Jump when the condition is Lua-false, meaning nil or false.",
    "JNZ": "Jump when the condition is Lua-truthy.",
    "JMP": "Jump to a label.",
    "LABEL": "A named point in the bytecode; execution falls through it.",
    "CLOSURE": "Create a function closure and capture any upvalue cells.",
    "MAKE_CELL": "Wrap a local value in a mutable cell so closures can share it.",
    "CELL_GET": "Read the current value from an upvalue cell.",
    "CELL_SET": "Write a new value into an upvalue cell.",
    "BIND_UPVALUE": "Bind this function's local cell register to a captured upvalue.",
    "PARAM": "Push one argument into the pending argument list.",
    "PARAM_EXPAND": "Push multiple values from a list-like result into arguments.",
    "CALL_VALUE": "Call a function value or builtin using the pending arguments.",
    "TAIL_CALL_VALUE": "Call in tail position, replacing the current frame when possible.",
    "ARG": "Move one incoming function argument into a local register.",
    "RESULT": "Read the first value returned by the previous call.",
    "RESULT_LIST": "Read all values returned by the previous call as a list.",
    "RETURN": "Return one value from the current function.",
    "RETURN_MULTI": "Return multiple values from the current function.",
    "TABLE_NEW": "Create a Lua table.",
    "TABLE_SET": "Write a key/value pair into a table.",
    "TABLE_GET": "Read a value from a table by key.",
    "TABLE_APPEND": "Append an array-style value to a table.",
    "HALT": "Stop the VM.",
}


def main() -> int:
    out_dir = pathlib.Path(__file__).resolve().parent
    demos = [record_demo(demo) for demo in DEMOS]
    payload = {
        "title": "Lua Bytecode VM Teaching Demo",
        "generatedBy": "docs/lua-vm-demo/export_demo.py",
        "opcodeExplanations": OPCODE_EXPLANATIONS,
        "demos": demos,
    }
    json_path = out_dir / "demo-data.json"
    js_path = out_dir / "demo-data.js"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_text + "\n", encoding="utf-8")
    js_path.write_text(
        "window.LUA_VM_DEMO_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {js_path}")
    return 0


def record_demo(demo: dict[str, Any]) -> dict[str, Any]:
    source = demo["source"]
    source_name = demo["source_name"]
    instructions = list(compile_source(source, source_name=source_name))
    env = create_default_environment()
    vm = BytecodeVM(instructions)
    vm.lua_env = env
    vm.registers.update(env.to_vm_registers())
    env.bind_vm(vm)
    vm.index_labels()

    initial_registers = dict(vm.registers)
    user_globals = collect_user_globals(instructions, initial_registers)
    steps: list[dict[str, Any]] = []
    previous_registers: dict[str, Any] | None = None
    previous_pc: int | None = None
    previous_opcode: str | None = None
    halted = False
    error: str | None = None

    try:
        steps.append(
            snapshot_step(
                vm,
                instructions,
                0,
                user_globals,
                previous_registers,
                previous_pc=previous_pc,
                previous_opcode=previous_opcode,
                status="ready",
            )
        )
        previous_registers = serialized_registers(vm, user_globals)
        max_steps = 500
        for step_index in range(1, max_steps + 1):
            if vm.pc >= len(instructions):
                halted = True
                break
            current_pc = vm.pc
            current_instruction = instructions[current_pc]
            control = vm.step()
            status = "halted" if control == "halt" else "running"
            steps.append(
                snapshot_step(
                    vm,
                    instructions,
                    step_index,
                    user_globals,
                    previous_registers,
                    previous_pc=current_pc,
                    previous_opcode=current_instruction.opcode.name,
                    status=status,
                )
            )
            previous_registers = serialized_registers(vm, user_globals)
            if control == "halt":
                halted = True
                break
        else:
            error = "Stopped after 500 steps; possible infinite loop."
    except VMRuntimeError as exc:
        error = str(exc)
        steps.append(
            snapshot_step(
                vm,
                instructions,
                len(steps),
                user_globals,
                previous_registers,
                previous_pc=vm.pc,
                previous_opcode=None,
                status="error",
                error=error,
            )
        )
    finally:
        env.unbind_vm()

    return {
        "id": demo["id"],
        "title": demo["title"],
        "summary": demo["summary"],
        "focus": demo["focus"],
        "sourceName": source_name,
        "source": source,
        "instructions": [serialize_instruction(index, inst) for index, inst in enumerate(instructions)],
        "labels": dict(vm.labels),
        "steps": steps,
        "halted": halted,
        "error": error,
    }


def collect_user_globals(instructions: list[Any], initial_registers: dict[str, Any]) -> set[str]:
    globals_seen: set[str] = set()
    builtin_globals = {
        name for name, value in initial_registers.items() if isinstance(value, BuiltinFunction)
    }
    for inst in instructions:
        args = list(getattr(inst, "args", []))
        if not args:
            continue
        opcode = getattr(inst, "opcode", None)
        opcode_name = getattr(opcode, "name", "")
        if opcode_name in {"MOV", "CLOSURE", "LOAD_CONST", "LOAD_IMM"}:
            first = args[0]
            if isinstance(first, str) and first.startswith("G_") and first not in builtin_globals:
                globals_seen.add(first)
        for arg in args:
            if isinstance(arg, str) and arg.startswith("G_") and arg not in builtin_globals:
                globals_seen.add(arg)
    return globals_seen


def snapshot_step(
    vm: BytecodeVM,
    instructions: list[Any],
    step_index: int,
    user_globals: set[str],
    previous_registers: dict[str, Any] | None,
    *,
    previous_pc: int | None,
    previous_opcode: str | None,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    snapshot = vm.snapshot_state()
    registers = serialized_registers(vm, user_globals)
    changed = sorted(
        name
        for name, value in registers.items()
        if previous_registers is not None and previous_registers.get(name) != value
    )
    current_instruction = (
        serialize_instruction(vm.pc, instructions[vm.pc])
        if 0 <= vm.pc < len(instructions)
        else None
    )
    return {
        "step": step_index,
        "status": status,
        "pc": vm.pc,
        "previousPc": previous_pc,
        "previousOpcode": previous_opcode,
        "currentInstruction": current_instruction,
        "currentSourceLine": current_source_line(instructions, vm.pc),
        "registers": [
            {"name": name, "value": value, "changed": name in changed}
            for name, value in sorted(registers.items())
        ],
        "changedRegisters": changed,
        "callStack": [serialize_trace_frame(frame) for frame in snapshot.call_stack],
        "upvalues": [serialize_value(value) for value in snapshot.upvalues],
        "output": [serialize_value(value) for value in snapshot.output],
        "returnValue": serialize_value(vm.return_value),
        "lastReturn": [serialize_value(value) for value in vm.last_return],
        "pendingParams": [serialize_value(value) for value in vm.pending_params],
        "paramStack": [serialize_value(value) for value in vm.param_stack],
        "error": error,
    }


def serialized_registers(vm: BytecodeVM, user_globals: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in vm.registers.items():
        if name.startswith("G_") and name not in user_globals:
            continue
        result[name] = serialize_value(value)
    return result


def serialize_instruction(index: int, inst: Any) -> dict[str, Any]:
    debug = getattr(inst, "debug", None)
    location = getattr(debug, "location", None) if debug is not None else None
    return {
        "pc": index,
        "opcode": inst.opcode.name,
        "args": [serialize_arg(arg) for arg in inst.args],
        "text": str(inst),
        "debug": None
        if debug is None or location is None
        else {
            "file": location.file,
            "line": location.line,
            "column": location.column,
            "function": debug.function_name,
        },
    }


def current_source_line(instructions: list[Any], pc: int) -> int | None:
    if not instructions:
        return None
    pc = min(max(pc, 0), len(instructions) - 1)
    for index in range(pc, -1, -1):
        debug = getattr(instructions[index], "debug", None)
        location = getattr(debug, "location", None) if debug is not None else None
        if location is not None and location.line:
            return int(location.line)
    return None


def serialize_trace_frame(frame: Any) -> dict[str, Any]:
    return {
        "function": getattr(frame, "function_name", "<chunk>"),
        "file": getattr(frame, "file", "<unknown>"),
        "line": getattr(frame, "line", 0),
        "column": getattr(frame, "column", 0),
        "pc": getattr(frame, "pc", 0),
    }


def serialize_arg(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return serialize_value(value)


def serialize_value(value: Any, *, depth: int = 0, seen: set[int] | None = None) -> Any:
    if seen is None:
        seen = set()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth > 4:
        return {"kind": "object", "repr": short_repr(value)}
    obj_id = id(value)
    if obj_id in seen:
        return {"kind": "ref", "repr": short_repr(value)}
    seen.add(obj_id)
    if isinstance(value, Cell):
        return {"kind": "cell", "value": serialize_value(value.value, depth=depth + 1, seen=seen)}
    if isinstance(value, BuiltinFunction):
        return {"kind": "builtin", "name": value.name}
    if isinstance(value, LuaTable):
        return serialize_lua_table(value, depth=depth, seen=seen)
    if isinstance(value, dict) and "label" in value:
        return {
            "kind": "closure",
            "label": value.get("label"),
            "debugName": value.get("debug_name"),
            "upvalues": [
                serialize_value(item, depth=depth + 1, seen=seen)
                for item in value.get("upvalues", [])
            ],
        }
    if isinstance(value, (list, tuple)):
        return [serialize_value(item, depth=depth + 1, seen=seen) for item in list(value)[:20]]
    if is_dataclass(value):
        return serialize_value(asdict(value), depth=depth + 1, seen=seen)
    if isinstance(value, dict):
        items = []
        for index, (key, item) in enumerate(value.items()):
            if index >= 20:
                break
            items.append(
                {
                    "key": serialize_value(key, depth=depth + 1, seen=seen),
                    "value": serialize_value(item, depth=depth + 1, seen=seen),
                }
            )
        return {"kind": "dict", "items": items}
    return {"kind": type(value).__name__, "repr": short_repr(value)}


def serialize_lua_table(value: LuaTable, *, depth: int, seen: set[int]) -> dict[str, Any]:
    array = [
        serialize_value(item, depth=depth + 1, seen=seen)
        for item in value.array[:12]
    ]
    mapping = []
    for index, (key, item) in enumerate(value.map.items()):
        if index >= 12:
            break
        mapping.append(
            {
                "key": serialize_value(key, depth=depth + 1, seen=seen),
                "value": serialize_value(item, depth=depth + 1, seen=seen),
            }
        )
    return {
        "kind": "table",
        "array": array,
        "map": mapping,
        "length": value.lua_len(),
    }


def short_repr(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 120 else text[:117] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
