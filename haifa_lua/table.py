from __future__ import annotations

from typing import Any, Dict, Iterable, List


class LuaTable:
    """Hybrid table supporting Lua-style array and dictionary access."""

    __slots__ = ("array", "map", "__lua_table__")

    def __init__(self, array: Iterable[Any] | None = None, mapping: Dict[Any, Any] | None = None) -> None:
        self.array: List[Any] = list(array) if array is not None else []
        self.map: Dict[Any, Any] = dict(mapping) if mapping is not None else {}
        self.__lua_table__ = True

    # ---------------------------- array helpers ---------------------------- #
    def append(self, value: Any) -> None:
        self.array.append(value)
        self._trim_array()

    def extend(self, values: Iterable[Any]) -> None:
        for value in values:
            self.array.append(value)
        self._trim_array()

    def insert(self, index: int, value: Any) -> None:
        if index < 1:
            index = 1
        if index > len(self.array) + 1:
            index = len(self.array) + 1
        self.array.insert(index - 1, value)
        self._trim_array()

    def remove(self, index: int | None = None) -> Any:
        if not self.array:
            return None
        if index is None:
            index = len(self.array)
        if index < 1 or index > len(self.array):
            return None
        value = self.array.pop(index - 1)
        self._trim_array()
        return value

    def lua_len(self) -> int:
        count = len(self.array)
        while count > 0 and self.array[count - 1] is None:
            count -= 1
        return count

    # --------------------------- raw table access -------------------------- #
    def raw_get(self, key: Any) -> Any:
        if self._is_array_key(key):
            index = int(key)
            if 1 <= index <= len(self.array):
                return self.array[index - 1]
        return self.map.get(key, None)

    def raw_set(self, key: Any, value: Any) -> None:
        if self._is_array_key(key):
            index = int(key)
            if 1 <= index <= len(self.array):
                self.array[index - 1] = value
                if value is None:
                    self._trim_array()
                return
            if index == len(self.array) + 1:
                if value is None:
                    return
                self.array.append(value)
                return
        if value is None:
            self.map.pop(key, None)
        else:
            self.map[key] = value


    # ---------------------------- iteration helpers --------------------------- #
    def iter_items(self):
        for idx, value in enumerate(self.array, start=1):
            if value is not None:
                yield idx, value
        for key, value in self.map.items():
            yield key, value


    # ------------------------------- internals ----------------------------- #
    def _trim_array(self) -> None:
        while self.array and self.array[-1] is None:
            self.array.pop()

    @staticmethod
    def _is_array_key(key: Any) -> bool:
        if isinstance(key, bool):
            return False
        if isinstance(key, int):
            return key >= 1
        if isinstance(key, float) and key.is_integer():
            return int(key) >= 1
        return False

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"LuaTable(array={self.array!r}, map={self.map!r})"


__all__ = ["LuaTable"]
