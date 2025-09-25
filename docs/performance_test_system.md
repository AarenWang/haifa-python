# haifa_lua 性能基准测试系统

## 🎯 系统概述

本测试系统旨在客观评估 haifa_lua 解释器相对于官方 Lua 解释器的性能表现，为性能优化提供数据支持和改进方向。

## 📁 文件结构

```
benchmark/
├── README.md                    # 使用指南
├── benchmark_runner.py          # 自动化测试执行器  
├── analyze_results.py           # 结果分析与报告生成器
├── scripts/                     # 测试脚本目录
│   ├── arithmetic_bench.lua     # 算术运算性能测试
│   ├── arithmetic_simple.lua    # 简化算术测试(兼容haifa_lua)
│   ├── function_bench.lua       # 函数调用性能测试
│   └── control_bench.lua        # 控制流性能测试
└── results/                     # 测试结果存储目录
    └── (生成的JSON结果文件)

docs/
└── performance_benchmark.md     # 详细测试方案文档
```

## 🚀 快速开始

### 1. 环境准备
```bash
# 安装官方 Lua 解释器
brew install lua  # macOS

# 安装 Python 依赖  
pip install psutil

# 进入项目目录
cd haifa-python
```

### 2. 运行基准测试
```bash
# 基础测试
python benchmark/benchmark_runner.py

# 高精度测试 (5次迭代)
python benchmark/benchmark_runner.py -i 5
```

### 3. 分析结果
```bash
# 生成详细报告
python benchmark/analyze_results.py benchmark/results/benchmark_results_YYYYMMDD_HHMMSS.json
```

## 📊 测试维度

### 核心测试项目

1. **算术运算测试** (`arithmetic_bench.lua`)
   - 整数运算: 加减乘除、取模运算
   - 浮点运算: 基础数学计算
   - **目标性能**: 达到官方解释器 60-80%

2. **函数调用测试** (`function_bench.lua`)  
   - 递归调用: 斐波那契数列计算
   - 迭代调用: 循环优化测试
   - 深度调用栈: 栈管理效率
   - **目标性能**: 达到官方解释器 50-70%

3. **控制流测试** (`control_bench.lua`)
   - 条件分支: if/elseif/else 性能
   - 嵌套循环: 多层循环优化
   - 复杂条件: 逻辑运算组合
   - **目标性能**: 达到官方解释器 60-80%

### 评估指标

- **执行时间**: 平均、最小、最大执行时间
- **性能比率**: haifa_lua 相对于官方 Lua 的倍数关系
- **相对性能**: haifa_lua 达到官方 Lua 的性能百分比
- **稳定性**: 多次执行的标准差

## 📈 性能等级标准

| 性能比率 | 相对性能 | 等级 | 评价 |
|----------|----------|------|------|
| 1.0x - 1.5x | >66% | 🟢 优秀 | 接近官方解释器水平 |
| 1.5x - 3.0x | 33-66% | 🟡 良好 | 适合大部分应用场景 |
| 3.0x - 5.0x | 20-33% | 🟠 一般 | 需要优化但仍可用 |
| >5.0x | <20% | 🔴 较差 | 需要重点优化 |

## 🔧 当前测试结果示例

基于简化测试脚本的初步结果：

```bash
$ lua benchmark/scripts/arithmetic_simple.lua
# Output: 算术运算完成，结果稳定

$ python -m haifa_lua.cli benchmark/scripts/arithmetic_simple.lua
# Output: Running arithmetic benchmark with operations...
# Results: Integer ops result: 325909950, Float ops result: 325909950
```

**观察结果**:
- ✅ haifa_lua 能够正确执行基础算术运算
- ✅ 计算结果与预期一致
- ⚠️ 需要完整计时比较才能得出性能差距

## 🛠️ 优化方向建议

基于测试框架设计，预期的优化重点：

### 1. 字节码执行优化
- **指令合并**: 将常用操作组合成单一指令
- **跳转优化**: 减少条件分支的开销
- **寄存器分配**: 优化虚拟寄存器使用效率

### 2. 内存管理优化  
- **对象池**: 复用常用对象类型
- **垃圾回收**: 优化 Python GC 对 VM 的影响
- **栈管理**: 减少函数调用时的栈操作

### 3. 类型系统优化
- **快速路径**: 为常见类型提供专用处理
- **类型推断**: 减少运行时类型检查
- **缓存机制**: 缓存类型转换结果

## 📋 使用注意事项

### 环境要求
- Python 3.8+
- Lua 5.4+ (用于对比测试)
- psutil 库 (用于内存监控)

### 兼容性说明
- 当前测试脚本需要适配 haifa_lua 的语法支持范围
- 部分高级语法 (如 `os.clock()`, `string.format()`) 可能需要简化
- 测试结果仅反映当前实现阶段的性能水平

### 扩展建议
1. **增加测试用例**: 根据实际应用场景添加更多测试
2. **长期监控**: 设置 CI 自动执行性能回归测试  
3. **细粒度分析**: 使用 profiler 分析具体瓶颈
4. **实际应用测试**: 使用真实 Lua 脚本进行端到端测试

## 🎯 里程碑目标

### 短期目标 (当前阶段)
- [ ] 基础算术运算达到官方解释器 70% 性能
- [ ] 函数调用达到官方解释器 60% 性能
- [ ] 建立完整的性能监控体系

### 中期目标 (优化阶段)  
- [ ] 综合性能达到官方解释器 50% 以上
- [ ] 内存使用控制在官方解释器 150% 以内
- [ ] 支持更多复杂语法的性能测试

### 长期目标 (成熟阶段)
- [ ] 核心功能性能达到官方解释器 80% 以上
- [ ] 实现 JIT 编译优化热点代码
- [ ] 建立性能基准数据库供社区参考

---

通过这套性能基准测试系统，我们可以：
1. **客观评估** haifa_lua 的当前性能水平
2. **识别瓶颈** 找出需要优化的关键部分  
3. **跟踪改进** 监控优化措施的效果
4. **指导开发** 为后续开发提供数据支持

这为 haifa_lua 项目的性能优化提供了科学的测量工具和改进方向。