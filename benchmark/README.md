# Lua 解释器性能基准测试使用指南

## 快速开始

### 1. 环境准备

```bash
# 安装官方 Lua 解释器 (用于对比)
brew install lua                    # macOS
# 或
sudo apt-get install lua5.4         # Ubuntu

# 安装 Python 依赖（可选，用于 analyze_results 等扩展工具）
pip install psutil

# 确保在项目根目录
cd haifa-python
```

### 2. 运行基准测试

```bash
# 基础测试 (3次迭代)
python benchmark/benchmark_runner.py

# 更精确的测试 (5次迭代)  
python benchmark/benchmark_runner.py -i 5

# 自定义输出文件名
python benchmark/benchmark_runner.py -o my_benchmark_results.json
```

### 3. 分析结果

```bash
# 生成详细分析报告
python benchmark/analyze_results.py benchmark/results/benchmark_results_YYYYMMDD_HHMMSS.json

# 报告将自动保存为同名的 .md 文件
```

## 测试项目说明

### 算术运算测试 (arithmetic_bench.lua)
- **测试内容**: 整数运算、浮点运算
- **评估指标**: 基础运算指令的执行效率
- **说明**: 单一脚本同时用于官方 Lua 与 haifa_lua，由运行器在外部计时
- **预期性能**: 目标达到官方解释器 60-80% 性能

### 函数调用测试 (function_bench.lua)
- **测试内容**: 递归调用、迭代调用、深度调用栈、简单函数调用
- **评估指标**: 函数调用开销、栈管理效率
- **说明**: 单一脚本同时用于官方 Lua 与 haifa_lua，由运行器在外部计时
- **预期性能**: 目标达到官方解释器 50-70% 性能

### 控制流测试 (control_bench.lua)
- **测试内容**: 条件分支、嵌套循环、while循环、复杂条件
- **评估指标**: 分支预测、循环优化效果
- **说明**: 单一脚本同时用于官方 Lua 与 haifa_lua，由运行器在外部计时
- **预期性能**: 目标达到官方解释器 60-80% 性能

## 结果解读

### 性能比率说明
- **1.0x - 1.5x**: 优秀，性能接近官方解释器
- **1.5x - 3.0x**: 良好，适合大部分应用场景  
- **3.0x - 5.0x**: 一般，需要优化但仍可用
- **5.0x+**: 较差，需要重点优化

### 典型输出示例

```
PERFORMANCE BENCHMARK SUMMARY
============================================================
Test Time: 2025-09-25 10:49:13
Iterations: 3
Lua Version: None

Test                 Lua (s)      haifa_lua (s)   Ratio    Performance
---------------------------------------------------------------------------
arithmetic_bench.lua N/A          4.6168          N/A      N/A
function_bench.lua   N/A          2.2248          N/A      N/A
control_bench.lua    N/A          7.6660          N/A      N/A

Overall Assessment:
  Official Lua interpreter missing — only haifa_lua timings recorded
```

## 故障排除

### 常见问题

1. **找不到 Lua 解释器**
   ```bash
   # 检查 Lua 是否已安装
   lua -v
   
   # macOS 安装
   brew install lua
   
   # Ubuntu 安装  
   sudo apt-get install lua5.4
   ```

2. **haifa_lua 模块导入失败**
   ```bash
   # 确保在正确目录
   ls haifa_lua/  # 应该看到 __init__.py 等文件
   
   # 检查 Python 路径
   python -c "import sys; print('\n'.join(sys.path))"
   ```

3. **测试脚本执行失败**
   ```bash
   # 手动测试单个脚本
   lua benchmark/scripts/arithmetic_bench.lua
   python -m haifa_lua.cli benchmark/scripts/arithmetic_bench.lua
   ```

### 性能调试

如果性能表现不佳，可以：

1. **使用 Python 分析器**:
   ```bash
   python -m cProfile -o profile.stats benchmark/benchmark_runner.py
   python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"
   ```

2. **启用详细输出**:
   ```bash
   # 在测试脚本中添加调试信息
   python benchmark/benchmark_runner.py --verbose
   ```

3. **分别测试各组件**:
   ```bash
   # 测试词法分析器
   python -c "from haifa_lua.lexer import LuaLexer; import time; ..."
   
   # 测试解析器  
   python -c "from haifa_lua.parser import LuaParser; import time; ..."
   ```

## 自定义测试

### 添加新测试脚本

1. 在 `benchmark/scripts/` 创建 `.lua` 文件
2. 确保脚本聚焦于构造工作负载（计时由 `benchmark_runner.py` 负责）
3. 将脚本名添加到 `benchmark_runner.py` 的 `test_scripts` 列表

### 测试脚本模板

```lua
-- 自定义测试脚本模板
local ITERATIONS = 100000

local function test_my_feature(n)
    local result = 0
    for i = 1, n do
        -- 测试逻辑
        result = result + i
    end
    return result
end

print("My Feature Test with " .. ITERATIONS .. " iterations")
local result = test_my_feature(ITERATIONS)
print("Result:")
print(result)
```

## 持续集成

可以将性能测试集成到 CI/CD 流程中：

```yaml
# .github/workflows/performance.yml
name: Performance Benchmark

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        sudo apt-get install -y lua5.4
        pip install psutil
    - name: Run benchmarks
      run: |
        python benchmark/benchmark_runner.py -i 3
    - name: Upload results
      uses: actions/upload-artifact@v3
      with:
        name: benchmark-results
        path: benchmark/results/
```

---

如有问题或建议，请提交 Issue 或 Pull Request。