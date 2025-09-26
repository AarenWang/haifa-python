from __future__ import annotations

import json
import re

from compiler.bytecode_vm import BytecodeVM
from haifa_jq.jq_bytecode import JQOpcode


class JQVM(BytecodeVM):
    """VM for jq bytecode.

    This class owns jq-specific opcode handlers and overrides the core
    dispatch table for those opcodes, keeping the core VM generic.
    """

    def __init__(self, instructions):
        super().__init__(instructions)
        # Override/extend handlers for jq-only opcodes
        self._handlers.update(
            {
                JQOpcode.OBJ_GET: self._op_OBJ_GET,
                JQOpcode.OBJ_SET: self._op_OBJ_SET,
                JQOpcode.SET_INDEX: self._op_SET_INDEX,
                JQOpcode.GET_INDEX: self._op_GET_INDEX,
                JQOpcode.LEN_VALUE: self._op_LEN_VALUE,
                JQOpcode.PUSH_EMIT: self._op_PUSH_EMIT,
                JQOpcode.POP_EMIT: self._op_POP_EMIT,
                JQOpcode.EMIT: self._op_EMIT,
                JQOpcode.TRY_BEGIN: self._op_TRY_BEGIN,
                JQOpcode.TRY_END: self._op_TRY_END,
                JQOpcode.FLATTEN: self._op_FLATTEN,
                JQOpcode.REDUCE: self._op_REDUCE,
                JQOpcode.KEYS: self._op_KEYS,
                JQOpcode.HAS: self._op_HAS,
                JQOpcode.CONTAINS: self._op_CONTAINS,
                JQOpcode.JOIN: self._op_JOIN,
                JQOpcode.REVERSE: self._op_REVERSE,
                JQOpcode.FIRST: self._op_FIRST,
                JQOpcode.LAST: self._op_LAST,
                JQOpcode.ANY: self._op_ANY,
                JQOpcode.ALL: self._op_ALL,
                JQOpcode.AGG_ADD: self._op_AGG_ADD,
                JQOpcode.SORT: self._op_SORT,
                JQOpcode.SORT_BY: self._op_SORT_BY,
                JQOpcode.UNIQUE: self._op_UNIQUE,
                JQOpcode.UNIQUE_BY: self._op_UNIQUE_BY,
                JQOpcode.MIN: self._op_MIN,
                JQOpcode.MAX: self._op_MAX,
                JQOpcode.MIN_BY: self._op_MIN_BY,
                JQOpcode.MAX_BY: self._op_MAX_BY,
                JQOpcode.GROUP_BY: self._op_GROUP_BY,
                JQOpcode.TOSTRING: self._op_TOSTRING,
                JQOpcode.TONUMBER: self._op_TONUMBER,
                JQOpcode.SPLIT: self._op_SPLIT,
                JQOpcode.GSUB: self._op_GSUB,
            }
        )

    # ---------- jq helpers ----------
    def _sort_key(self, x):
        if x is None:
            return (0, 0)
        if isinstance(x, bool):
            return (1, int(x))
        if isinstance(x, (int, float)):
            return (2, x)
        if isinstance(x, str):
            return (3, x)
        if isinstance(x, list):
            try:
                return (4, [self._sort_key(v) for v in x])
            except Exception:
                return (4, len(x))
        if isinstance(x, dict):
            try:
                items = sorted((str(k), x[k]) for k in x.keys())
                return (5, [(k, self._sort_key(v)) for k, v in items])
            except Exception:
                return (5, json.dumps(x, sort_keys=True, ensure_ascii=False))
        return (6, str(x))

    # ---------- jq opcode handlers ----------
    def _op_OBJ_GET(self, args):
        source = self.val(args[1])
        key = args[2]
        if isinstance(source, dict) and key in source:
            self.registers[args[0]] = source[key]
        else:
            self.registers[args[0]] = None

    def _op_OBJ_SET(self, args):
        obj = self.registers.get(args[0])
        if not isinstance(obj, dict):
            obj = {}
            self.registers[args[0]] = obj
        obj[args[1]] = self.val(args[2])

    def _op_SET_INDEX(self, args):
        container = self.registers.get(args[0])
        index_value = self.val(args[1])
        value = self.val(args[2])
        if isinstance(container, list):
            try:
                idx = int(index_value)
            except Exception:
                return
            length = len(container)
            if idx < 0:
                idx += length
            if 0 <= idx < length:
                container[idx] = value
            elif idx == length:
                container.append(value)

    def _op_GET_INDEX(self, args):
        container = self.val(args[1])
        index = int(self.val(args[2]))
        value = None
        if isinstance(container, (list, tuple)) and -len(container) <= index < len(container):
            value = container[index]
        self.registers[args[0]] = value

    def _op_LEN_VALUE(self, args):
        value = self.val(args[1])
        try:
            self.registers[args[0]] = len(value)
        except (TypeError, ValueError):
            self.registers[args[0]] = 0

    def _op_PUSH_EMIT(self, args):
        self.emit_stack.append(args[0])

    def _op_POP_EMIT(self, args):
        if self.emit_stack:
            self.emit_stack.pop()

    def _op_EMIT(self, args):
        value = self.val(args[0])
        if self.emit_stack:
            target = self.emit_stack[-1]
            container = self.registers.get(target)
            if not isinstance(container, list):
                container = [] if container is None else list(container if isinstance(container, list) else [container])
            container.append(value)
            self.registers[target] = container
        else:
            self.output.append(value)

    def _op_TRY_BEGIN(self, args):
        catch_label, error_reg, buffer_reg = args
        emit_depth = max(len(self.emit_stack) - 1, 0)
        self.try_stack.append((catch_label, error_reg, emit_depth, buffer_reg))

    def _op_TRY_END(self, args):
        if self.try_stack:
            self.try_stack.pop()


    def _op_FLATTEN(self, args):
        value = self.val(args[1])
        if isinstance(value, list):
            flattened = []
            for item in value:
                if isinstance(item, list):
                    flattened.extend(item)
                else:
                    flattened.append(item)
        elif value is None:
            flattened = []
        else:
            flattened = value
        self.registers[args[0]] = flattened

    def _op_REDUCE(self, args):
        items_source = self.val(args[1])
        if isinstance(items_source, (list, tuple)):
            items = list(items_source)
        elif items_source is None:
            items = []
        else:
            items = [items_source]
        op_name = str(args[2]).lower()
        has_initial = len(args) > 3 and args[3] not in (None, "")
        initial_value = self.val(args[3]) if has_initial else None

        if op_name == "sum":
            acc = initial_value if has_initial else 0
            for item in items:
                if item is not None:
                    acc += item
        elif op_name == "product":
            acc = initial_value if has_initial else 1
            for item in items:
                if item is not None:
                    acc *= item
        elif op_name == "min":
            if has_initial:
                acc = initial_value
            elif items:
                acc = items[0]
                items = items[1:]
            else:
                acc = None
            for item in items:
                if acc is None or (item is not None and item < acc):
                    acc = item
        elif op_name == "max":
            if has_initial:
                acc = initial_value
            elif items:
                acc = items[0]
                items = items[1:]
            else:
                acc = None
            for item in items:
                if acc is None or (item is not None and item > acc):
                    acc = item
        elif op_name == "concat":
            if has_initial:
                acc = initial_value
            else:
                acc = []
            if acc is None:
                acc = []
            if not isinstance(acc, list):
                acc = [acc]
            for item in items:
                if isinstance(item, list):
                    acc.extend(item)
                elif item is not None:
                    acc.append(item)
        else:
            raise RuntimeError(f"Unsupported reduce operation: {op_name}")
        self.registers[args[0]] = acc

    def _op_KEYS(self, args):
        src = self.val(args[1])
        keys = []
        if isinstance(src, dict):
            try:
                keys = sorted(list(src.keys()))
            except Exception:
                keys = list(src.keys())
        elif isinstance(src, (list, tuple)):
            keys = list(range(len(src)))
        self.registers[args[0]] = keys

    def _op_HAS(self, args):
        container = self.val(args[1])
        needle = self.val(args[2])
        result = False
        if isinstance(container, dict) and isinstance(needle, str):
            result = needle in container
        elif isinstance(container, (list, tuple)):
            try:
                idx = int(needle)
                result = -len(container) <= idx < len(container)
            except Exception:
                result = False
        self.registers[args[0]] = int(result)

    def _op_CONTAINS(self, args):
        container = self.val(args[1])
        needle = self.val(args[2])
        result = False
        if isinstance(container, str) and isinstance(needle, str):
            result = needle in container
        elif isinstance(container, list):
            try:
                result = any(item == needle for item in container)
            except Exception:
                result = False
        elif isinstance(container, dict):
            if isinstance(needle, str):
                result = needle in container
            elif isinstance(needle, dict):
                result = all(k in container and container[k] == v for k, v in needle.items())
        self.registers[args[0]] = int(result)

    def _op_JOIN(self, args):
        arr = self.val(args[1])
        sep = str(self.val(args[2]))
        if isinstance(arr, list):
            try:
                s = sep.join(str(x) if x is not None else "null" for x in arr)
            except Exception:
                s = sep.join(map(str, arr))
            self.registers[args[0]] = s
        else:
            self.registers[args[0]] = ""

    def _op_REVERSE(self, args):
        val = self.val(args[1])
        if isinstance(val, list):
            self.registers[args[0]] = list(reversed(val))
        elif isinstance(val, str):
            self.registers[args[0]] = val[::-1]
        else:
            self.registers[args[0]] = val

    def _op_FIRST(self, args):
        val = self.val(args[1])
        out = None
        if isinstance(val, list):
            out = val[0] if val else None
        elif isinstance(val, str):
            out = val[0] if val else None
        self.registers[args[0]] = out

    def _op_LAST(self, args):
        val = self.val(args[1])
        out = None
        if isinstance(val, list):
            out = val[-1] if val else None
        elif isinstance(val, str):
            out = val[-1] if val else None
        self.registers[args[0]] = out

    def _op_ANY(self, args):
        val = self.val(args[1])
        if isinstance(val, list):
            self.registers[args[0]] = int(any(bool(x) for x in val))
        else:
            self.registers[args[0]] = int(bool(val))

    def _op_ALL(self, args):
        val = self.val(args[1])
        if isinstance(val, list):
            self.registers[args[0]] = int(all(bool(x) for x in val))
        else:
            self.registers[args[0]] = int(bool(val))

    def _op_AGG_ADD(self, args):
        val = self.val(args[1])
        out = None
        if isinstance(val, list):
            if all(isinstance(x, (int, float, bool)) for x in val):
                s = 0
                for x in val:
                    if x is not None:
                        s += x
                out = s
            elif all(isinstance(x, str) for x in val):
                out = "".join(val)
            elif all(isinstance(x, list) for x in val):
                res = []
                for x in val:
                    res.extend(x)
                out = res
        self.registers[args[0]] = out

    def _op_SORT(self, args):
        src = self.val(args[1])
        if isinstance(src, list):
            out = sorted(src, key=self._sort_key)
        else:
            out = src
        self.registers[args[0]] = out

    def _op_SORT_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        if isinstance(src, list) and isinstance(keys, list):
            pairs = list(zip(keys, src))
            pairs.sort(key=lambda kv: self._sort_key(kv[0]))
            out = [v for _, v in pairs]
        else:
            out = src
        self.registers[args[0]] = out

    def _op_UNIQUE(self, args):
        src = self.val(args[1])
        if isinstance(src, list):
            seen = []
            out = []
            for v in src:
                if not any(v == s for s in seen):
                    seen.append(v)
                    out.append(v)
        else:
            out = src
        self.registers[args[0]] = out

    def _op_UNIQUE_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        if isinstance(src, list) and isinstance(keys, list):
            seen = []
            out = []
            for k, v in zip(keys, src):
                sk = self._sort_key(k)
                if sk not in seen:
                    seen.append(sk)
                    out.append(v)
        else:
            out = src
        self.registers[args[0]] = out

    def _op_MIN(self, args):
        src = self.val(args[1])
        out = None
        if isinstance(src, list) and src:
            out = min(src, key=self._sort_key)
        self.registers[args[0]] = out

    def _op_MAX(self, args):
        src = self.val(args[1])
        out = None
        if isinstance(src, list) and src:
            out = max(src, key=self._sort_key)
        self.registers[args[0]] = out

    def _op_MIN_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        out = None
        if isinstance(src, list) and isinstance(keys, list) and src:
            idx = min(range(len(src)), key=lambda i: self._sort_key(keys[i]))
            out = src[idx]
        self.registers[args[0]] = out

    def _op_MAX_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        out = None
        if isinstance(src, list) and isinstance(keys, list) and src:
            idx = max(range(len(src)), key=lambda i: self._sort_key(keys[i]))
            out = src[idx]
        self.registers[args[0]] = out

    def _op_GROUP_BY(self, args):
        src = self.val(args[1])
        keys = self.registers.get(args[2])
        out = []
        if isinstance(src, list) and isinstance(keys, list):
            pairs = list(zip(keys, src))
            pairs.sort(key=lambda kv: self._sort_key(kv[0]))
            current_key = object()
            bucket = []
            for k, v in pairs:
                sk = self._sort_key(k)
                if bucket and sk != current_key:
                    out.append(bucket)
                    bucket = []
                current_key = sk
                bucket.append(v)
            if bucket:
                out.append(bucket)
        self.registers[args[0]] = out

    def _op_TOSTRING(self, args):
        val = self.val(args[1])
        if isinstance(val, str):
            self.registers[args[0]] = val
            return
        try:
            s = json.dumps(val, ensure_ascii=False)
        except Exception:
            s = str(val)
        self.registers[args[0]] = s

    def _op_TONUMBER(self, args):
        val = self.val(args[1])
        out = None
        try:
            if isinstance(val, (int, float)):
                out = val
            elif isinstance(val, bool):
                out = 1 if val else 0
            elif isinstance(val, str):
                try:
                    out = json.loads(val)
                    if not isinstance(out, (int, float)):
                        out = float(val) if val.strip() else None
                except Exception:
                    out = float(val) if val.strip() else None
            else:
                out = None
        except Exception:
            out = None
        self.registers[args[0]] = out

    def _op_SPLIT(self, args):
        s = self.val(args[1])
        sep = self.val(args[2])
        if isinstance(s, str) and isinstance(sep, str):
            parts = s.split(sep)
        else:
            parts = []
        self.registers[args[0]] = parts

    def _op_GSUB(self, args):
        s = self.val(args[1])
        pat = self.val(args[2])
        repl = self.val(args[3])
        if isinstance(s, str) and isinstance(pat, str) and isinstance(repl, str):
            try:
                out = re.sub(pat, repl, s)
            except re.error:
                out = s
        else:
            out = s
        self.registers[args[0]] = out


__all__ = ["JQVM"]
