# CS:APP 风格 Cache 存储层次与局部性模拟器规划

## 1. 背景与目标

本方案源自经典的 《CS:APP》（*Computer Systems: A Programmer's Perspective*）第 6 章及经典实验 **Cache Lab**。

### 核心定位
在本项目中实现一个参数化、教学透明、具备高保真度硬件行为的高速缓存模拟器（Cache Simulator），使学习者能够清晰观察：
1. CPU 发出内存读写请求（`LDR`/`STR`）时，物理地址如何被拆解为 **Tag（标记）**、**Set Index（组索引）** 与 **Block Offset（块内偏移）**。
2. 缓存的 **命中（Hit）**、**缺失（Miss）** 与 **淘汰（Eviction）** 判定。
3. 现代主流缓存策略：**LRU 替换算法** 与 **写回（Write-Back）+ 写分配（Write-Allocate）** 机制。
4. 程序的**时间局部性**与**空间局部性**（如二维数组行优先 vs 列优先遍历）对缓存命中率及运行周期的决定性影响。

---

## 2. 缓存数学模型与参数约定

遵循 CS:APP 标准表示法 $(S, E, B, m)$：
- $m$：物理地址总位数（默认 64 位）。
- $s$：组索引位数（组数 $S = 2^s$）。
- $b$：块偏移位数（块大小 $B = 2^b$ 字节）。
- $t = m - (s + b)$：标记位数。
- $E$：相联度（每组行数；$E=1$ 为直接映射，$E>1$ 为组相联，$S=1$ 为全相联）。

### 地址拆解格式
```
 63                                    s+b   s+b-1         b   b-1        0
+------------------------------------------+---------------+---------------+
|                Tag (t bits)              | Set (s bits)  | Offset (b bits)
+------------------------------------------+---------------+---------------+
```

---

## 3. 架构与目录设计

在 `arm_emulator/` 下创建独立的 `cache/` 子模块：

```
arm_emulator/
├── cache/
│   ├── __init__.py
│   ├── cache_line.py        # 缓存行（valid, dirty, tag, lru_counter, data）
│   ├── cache_set.py         # 缓存组（包含 E 条 Line，执行 LRU 命中/换出）
│   ├── cache_simulator.py   # 核心模拟器（地址位运算、读写流水线、统计）
│   ├── cached_memory.py     # 统一内存适配层（包装 Memory，透明拦截读写）
│   └── report.py            # 统计指标与教学报告（Hit Rate, Misses, Cycles）
└── tests/
    └── test_cache.py        # 针对 Cache 各特性的完备单元测试
```

---

## 4. 任务清单与实施里程碑

### Phase 1：核心缓存模型与位运算
- [ ] 定义 `CacheLine` 数据类（支持 `valid`、`dirty`、`tag`、`last_access_time`、`data: bytearray`）。
- [ ] 定义 `CacheSet` 类（维护 $E$ 条 Line，实现快速 Tag 查找、空闲行判定与 LRU 淘汰）。
- [ ] 实现 `CacheSimulator`：
  - [ ] 严格的位运算地址拆解（`tag`、`set_index`、`block_offset`、`block_aligned_addr`）。
  - [ ] 读操作流程（Read Hit / Cold Miss / Conflict Miss / 脏块写回底层主存）。
  - [ ] 写操作流程（Write-Back + Write-Allocate，标记 Dirty，写缺失先拉取整块）。
- [ ] 实现 `CacheStats` 与 `CacheReport`（包含 Hit/Miss 计数、命中率、脏块回写数、估算访问周期）。

### Phase 2：单元测试与算法验证
- [ ] 基础命中与缺失测试（直接映射 $E=1$ 与组相联 $E>1$）。
- [ ] LRU 淘汰顺序严格验证（连续访问更新热度，确保最久未访问行优先换出）。
- [ ] 写回（Write-Back）机制验证（脏块被逐出时正确写回底层主存，未修改块逐出时不触发写回）。
- [ ] 跨块与对齐边界读写测试（8/16/32/64 位宽度读取跨偏移）。

### Phase 3：内存适配器与执行器集成
- [ ] 实现 `CachedMemory`：封装现有 `arm_emulator.memory.Memory`，提供透明的 `read_byte/read_u64/write_u64` 等接口。
- [ ] 在 `arm_emulator.executor.Executor` 中支持挂载 `CachedMemory`。

### Phase 4：局部性经典实验与基准
- [ ] 编写 CS:APP 经典空间局部性测试（行优先 vs 列优先矩阵扫描）。
- [ ] 验证行优先的高命中率（~87.5% 以上）与列优先的高缺失率（~0%）。

---

## 5. 验收标准

1. `pytest` 跑通所有 Cache 核心用例与全量测试套件。
2. 缓存行为严格符合 CS:APP 规范，LRU 与 Write-back 数据不丢失。
3. 提供清晰友好的可读文本报告供教学使用。
