# Lua 解释器性能基准测试方案

## 1. 测试目标

本文档描述了用于对比 Lua 官方解释器 (PUC-Rio Lua) 和 haifa_lua 解释器性能的基准测试方案。

### 1.1 测试范围
- **执行性能**: 算术运算、控制流、函数调用等核心操作的执行速度
- **内存使用**: 内存占用量、垃圾回收效率
- **启动性能**: 解释器初始化和脚本加载时间
- **可扩展性**: 在不同数据规模下的性能表现

### 1.2 对比基准
- **Lua 5.4.x**: 官方最新稳定版本
- **haifa_lua**: 当前实现版本
- **性能目标**: haifa_lua 在核心功能上达到官方解释器 50-80% 的性能

## 2. 测试环境配置

### 2.1 硬件环境
```bash
# 系统信息收集
uname -a
system_profiler SPHardwareDataType  # macOS
cat /proc/cpuinfo                   # Linux
```

### 2.2 软件环境
```bash
# Lua 官方解释器安装
brew install lua                    # macOS
apt-get install lua5.4             # Ubuntu

# Python 环境
python --version
pip list | grep -E "(pytest|psutil|memory_profiler)"

# 确保测试一致性
export PYTHONHASHSEED=0
ulimit -v 8388608  # 限制虚拟内存 8GB
```

### 2.3 测试数据准备
```bash
# 创建测试数据目录
mkdir -p benchmark/data
mkdir -p benchmark/results
mkdir -p benchmark/scripts
```

## 3. 基准测试用例设计

### 3.1 算术运算性能 (arithmetic_bench.lua)
```lua
-- 测试整数运算
function test_integer_ops(n)
    local sum = 0
    local start_time = os.clock()
    
    for i = 1, n do
        sum = sum + i * 2 - 1
        sum = sum % 1000000
    end
    
    local end_time = os.clock()
    return end_time - start_time, sum
end

-- 测试浮点运算
function test_float_ops(n)
    local sum = 0.0
    local start_time = os.clock()
    
    for i = 1, n do
        sum = sum + math.sin(i / 1000.0) * math.cos(i / 1000.0)
    end
    
    local end_time = os.clock()
    return end_time - start_time, sum
end

-- 执行测试
local n = 1000000
local int_time, int_result = test_integer_ops(n)
local float_time, float_result = test_float_ops(n)

print(string.format("Integer ops: %.4f seconds, result: %d", int_time, int_result))
print(string.format("Float ops: %.4f seconds, result: %.6f", float_time, float_result))
```

### 3.2 函数调用性能 (function_bench.lua)
```lua
-- 递归函数测试
function fibonacci_recursive(n)
    if n <= 1 then
        return n
    end
    return fibonacci_recursive(n-1) + fibonacci_recursive(n-2)
end

-- 迭代函数测试
function fibonacci_iterative(n)
    if n <= 1 then return n end
    
    local a, b = 0, 1
    for i = 2, n do
        a, b = b, a + b
    end
    return b
end

-- 深层调用栈测试
function deep_call(depth)
    if depth <= 0 then
        return 1
    end
    return depth + deep_call(depth - 1)
end

-- 执行测试
local start_time = os.clock()
local result1 = fibonacci_recursive(30)
local recursive_time = os.clock() - start_time

start_time = os.clock()
local result2 = fibonacci_iterative(1000000)
local iterative_time = os.clock() - start_time

start_time = os.clock()
local result3 = deep_call(5000)
local deep_call_time = os.clock() - start_time

print(string.format("Recursive fib(30): %.4f seconds, result: %d", recursive_time, result1))
print(string.format("Iterative fib(1M): %.4f seconds, result: %d", iterative_time, result2))
print(string.format("Deep call(5000): %.4f seconds, result: %d", deep_call_time, result3))
```

### 3.3 表操作性能 (table_bench.lua)
```lua
-- 表创建和访问测试
function test_table_operations(n)
    local start_time = os.clock()
    
    -- 创建表
    local t = {}
    for i = 1, n do
        t[i] = i * 2
        t["key_" .. i] = "value_" .. i
    end
    
    -- 访问表
    local sum = 0
    for i = 1, n do
        sum = sum + t[i]
    end
    
    local end_time = os.clock()
    return end_time - start_time, sum, #t
end

-- 表遍历性能
function test_table_iteration(n)
    local t = {}
    for i = 1, n do
        t[i] = i
    end
    
    local start_time = os.clock()
    local sum = 0
    
    -- 数值遍历
    for i = 1, #t do
        sum = sum + t[i]
    end
    
    local pairs_sum = 0
    -- pairs 遍历
    for k, v in pairs(t) do
        pairs_sum = pairs_sum + v
    end
    
    local end_time = os.clock()
    return end_time - start_time, sum, pairs_sum
end

-- 执行测试
local n = 100000
local create_time, sum, size = test_table_operations(n)
local iter_time, sum1, sum2 = test_table_iteration(n)

print(string.format("Table create/access: %.4f seconds, sum: %d, size: %d", create_time, sum, size))
print(string.format("Table iteration: %.4f seconds, sum1: %d, sum2: %d", iter_time, sum1, sum2))
```

### 3.4 字符串操作性能 (string_bench.lua)
```lua
-- 字符串拼接测试
function test_string_concat(n)
    local start_time = os.clock()
    
    local str = ""
    for i = 1, n do
        str = str .. "a"
    end
    
    local end_time = os.clock()
    return end_time - start_time, #str
end

-- 字符串操作测试
function test_string_operations(n)
    local test_str = "Hello World! This is a test string for performance benchmarking."
    
    local start_time = os.clock()
    
    for i = 1, n do
        local upper = string.upper(test_str)
        local lower = string.lower(test_str)
        local sub = string.sub(test_str, 1, 10)
        local len = string.len(test_str)
    end
    
    local end_time = os.clock()
    return end_time - start_time
end

-- 执行测试
local n = 10000
local concat_time, str_len = test_string_concat(n)
local ops_time = test_string_operations(100000)

print(string.format("String concat: %.4f seconds, length: %d", concat_time, str_len))
print(string.format("String operations: %.4f seconds", ops_time))
```

### 3.5 控制流性能 (control_bench.lua)
```lua
-- 条件分支测试
function test_conditionals(n)
    local start_time = os.clock()
    local sum = 0
    
    for i = 1, n do
        if i % 5 == 0 then
            sum = sum + 5
        elseif i % 3 == 0 then
            sum = sum + 3
        elseif i % 2 == 0 then
            sum = sum + 2
        else
            sum = sum + 1
        end
    end
    
    local end_time = os.clock()
    return end_time - start_time, sum
end

-- 循环嵌套测试
function test_nested_loops(n)
    local start_time = os.clock()
    local sum = 0
    
    for i = 1, n do
        for j = 1, 10 do
            for k = 1, 5 do
                sum = sum + i + j + k
            end
        end
    end
    
    local end_time = os.clock()
    return end_time - start_time, sum
end

-- 执行测试
local n = 100000
local cond_time, cond_sum = test_conditionals(n)
local loop_time, loop_sum = test_nested_loops(1000)

print(string.format("Conditionals: %.4f seconds, sum: %d", cond_time, cond_sum))
print(string.format("Nested loops: %.4f seconds, sum: %d", loop_time, loop_sum))
```

## 4. 自动化测试框架

### 4.1 性能测试执行器 (benchmark_runner.py)
```python
#!/usr/bin/env python3
"""
Lua 解释器性能基准测试执行器
"""

import os
import sys
import time
import subprocess
import json
import psutil
from pathlib import Path
from typing import Dict, List, Tuple

class LuaBenchmarkRunner:
    def __init__(self, benchmark_dir: str = "benchmark"):
        self.benchmark_dir = Path(benchmark_dir)
        self.results_dir = self.benchmark_dir / "results"
        self.scripts_dir = self.benchmark_dir / "scripts"
        
        # 确保目录存在
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
    
    def run_lua_official(self, script_path: str) -> Tuple[float, str, Dict]:
        """运行官方 Lua 解释器"""
        process = psutil.Popen(
            ["lua", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 监控内存使用
        memory_samples = []
        start_time = time.perf_counter()
        
        while process.poll() is None:
            try:
                memory_info = process.memory_info()
                memory_samples.append(memory_info.rss / 1024 / 1024)  # MB
                time.sleep(0.01)
            except psutil.NoSuchProcess:
                break
        
        stdout, stderr = process.communicate()
        end_time = time.perf_counter()
        
        execution_time = end_time - start_time
        max_memory = max(memory_samples) if memory_samples else 0
        
        return execution_time, stdout, {
            "max_memory_mb": max_memory,
            "return_code": process.returncode
        }
    
    def run_haifa_lua(self, script_path: str) -> Tuple[float, str, Dict]:
        """运行 haifa_lua 解释器"""
        process = psutil.Popen(
            ["python", "-m", "haifa_lua.cli", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(Path(__file__).parent.parent)
        )
        
        # 监控内存使用
        memory_samples = []
        start_time = time.perf_counter()
        
        while process.poll() is None:
            try:
                # 包括子进程的内存使用
                memory_info = process.memory_info()
                memory_samples.append(memory_info.rss / 1024 / 1024)  # MB
                time.sleep(0.01)
            except psutil.NoSuchProcess:
                break
        
        stdout, stderr = process.communicate()
        end_time = time.perf_counter()
        
        execution_time = end_time - start_time
        max_memory = max(memory_samples) if memory_samples else 0
        
        return execution_time, stdout, {
            "max_memory_mb": max_memory,
            "return_code": process.returncode
        }
    
    def run_benchmark_suite(self, iterations: int = 5) -> Dict:
        """运行完整的基准测试套件"""
        test_scripts = [
            "arithmetic_bench.lua",
            "function_bench.lua", 
            "table_bench.lua",
            "string_bench.lua",
            "control_bench.lua"
        ]
        
        results = {
            "test_info": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "iterations": iterations,
                "python_version": sys.version,
                "system": os.uname()._asdict() if hasattr(os, 'uname') else str(os.name)
            },
            "tests": {}
        }
        
        for script in test_scripts:
            script_path = self.scripts_dir / script
            if not script_path.exists():
                print(f"Warning: {script} not found, skipping...")
                continue
            
            print(f"\nRunning {script}...")
            
            # 运行多次取平均值
            lua_times = []
            haifa_times = []
            lua_memories = []
            haifa_memories = []
            
            for i in range(iterations):
                print(f"  Iteration {i+1}/{iterations}")
                
                # 官方 Lua
                try:
                    exec_time, output, stats = self.run_lua_official(str(script_path))
                    lua_times.append(exec_time)
                    lua_memories.append(stats["max_memory_mb"])
                except Exception as e:
                    print(f"    Lua official failed: {e}")
                
                # haifa_lua
                try:
                    exec_time, output, stats = self.run_haifa_lua(str(script_path))
                    haifa_times.append(exec_time)
                    haifa_memories.append(stats["max_memory_mb"])
                except Exception as e:
                    print(f"    haifa_lua failed: {e}")
                
                time.sleep(0.5)  # 冷却时间
            
            # 计算统计结果
            results["tests"][script] = {
                "lua_official": {
                    "avg_time": sum(lua_times) / len(lua_times) if lua_times else 0,
                    "min_time": min(lua_times) if lua_times else 0,
                    "max_time": max(lua_times) if lua_times else 0,
                    "avg_memory": sum(lua_memories) / len(lua_memories) if lua_memories else 0
                },
                "haifa_lua": {
                    "avg_time": sum(haifa_times) / len(haifa_times) if haifa_times else 0,
                    "min_time": min(haifa_times) if haifa_times else 0,
                    "max_time": max(haifa_times) if haifa_times else 0,
                    "avg_memory": sum(haifa_memories) / len(haifa_memories) if haifa_memories else 0
                }
            }
            
            # 计算性能比率
            if lua_times and haifa_times:
                lua_avg = sum(lua_times) / len(lua_times)
                haifa_avg = sum(haifa_times) / len(haifa_times)
                results["tests"][script]["performance_ratio"] = haifa_avg / lua_avg
        
        return results
    
    def save_results(self, results: Dict, filename: str = None):
        """保存测试结果"""
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_results_{timestamp}.json"
        
        result_path = self.results_dir / filename
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {result_path}")
        return result_path

if __name__ == "__main__":
    runner = LuaBenchmarkRunner()
    results = runner.run_benchmark_suite(iterations=3)
    runner.save_results(results)
```

### 4.2 结果分析器 (analyze_results.py)
```python
#!/usr/bin/env python3
"""
性能测试结果分析与报告生成
"""

import json
import sys
from pathlib import Path
from typing import Dict

def generate_performance_report(results_file: str):
    """生成性能分析报告"""
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    print("# Lua 解释器性能基准测试报告\n")
    
    # 测试环境信息
    test_info = results.get("test_info", {})
    print("## 测试环境")
    print(f"- 测试时间: {test_info.get('timestamp', 'Unknown')}")
    print(f"- 测试轮次: {test_info.get('iterations', 'Unknown')}")
    print(f"- Python 版本: {test_info.get('python_version', 'Unknown')}")
    print(f"- 操作系统: {test_info.get('system', 'Unknown')}")
    print()
    
    # 性能对比表
    print("## 性能对比结果\n")
    print("| 测试用例 | Lua 官方 (秒) | haifa_lua (秒) | 性能比率 | 内存对比 (MB) |")
    print("|----------|---------------|----------------|----------|---------------|")
    
    total_ratio = 0
    test_count = 0
    
    for test_name, test_data in results.get("tests", {}).items():
        lua_time = test_data.get("lua_official", {}).get("avg_time", 0)
        haifa_time = test_data.get("haifa_lua", {}).get("avg_time", 0)
        ratio = test_data.get("performance_ratio", 0)
        
        lua_memory = test_data.get("lua_official", {}).get("avg_memory", 0)
        haifa_memory = test_data.get("haifa_lua", {}).get("avg_memory", 0)
        
        print(f"| {test_name} | {lua_time:.4f} | {haifa_time:.4f} | {ratio:.2f}x | {lua_memory:.1f} / {haifa_memory:.1f} |")
        
        if ratio > 0:
            total_ratio += ratio
            test_count += 1
    
    if test_count > 0:
        avg_ratio = total_ratio / test_count
        print(f"\n**平均性能比率**: {avg_ratio:.2f}x (haifa_lua 相对于官方 Lua)")
        
        performance_pct = (1 / avg_ratio) * 100 if avg_ratio > 0 else 0
        print(f"**相对性能**: {performance_pct:.1f}% (haifa_lua 达到官方 Lua 的性能百分比)")
    
    # 详细分析
    print("\n## 详细分析\n")
    
    for test_name, test_data in results.get("tests", {}).items():
        print(f"### {test_name}\n")
        
        lua_data = test_data.get("lua_official", {})
        haifa_data = test_data.get("haifa_lua", {})
        
        print(f"**Lua 官方解释器:**")
        print(f"- 平均执行时间: {lua_data.get('avg_time', 0):.4f} 秒")
        print(f"- 最短时间: {lua_data.get('min_time', 0):.4f} 秒")
        print(f"- 最长时间: {lua_data.get('max_time', 0):.4f} 秒") 
        print(f"- 平均内存使用: {lua_data.get('avg_memory', 0):.1f} MB")
        print()
        
        print(f"**haifa_lua 解释器:**")
        print(f"- 平均执行时间: {haifa_data.get('avg_time', 0):.4f} 秒")
        print(f"- 最短时间: {haifa_data.get('min_time', 0):.4f} 秒")
        print(f"- 最长时间: {haifa_data.get('max_time', 0):.4f} 秒")
        print(f"- 平均内存使用: {haifa_data.get('avg_memory', 0):.1f} MB")
        print()
        
        ratio = test_data.get('performance_ratio', 0)
        if ratio > 0:
            if ratio < 1.5:
                level = "优秀"
            elif ratio < 3.0:
                level = "良好"
            elif ratio < 5.0:
                level = "一般"
            else:
                level = "需要优化"
            
            print(f"**性能评级**: {level} (比率: {ratio:.2f}x)")
        print()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python analyze_results.py <results_file.json>")
        sys.exit(1)
    
    generate_performance_report(sys.argv[1])
```

## 5. 使用说明

### 5.1 环境准备
```bash
# 1. 安装依赖
pip install psutil memory_profiler

# 2. 安装官方 Lua 解释器
brew install lua  # macOS
# 或
sudo apt-get install lua5.4  # Ubuntu

# 3. 创建测试脚本
cd haifa-python
mkdir -p benchmark/{scripts,results,data}
```

### 5.2 创建测试脚本
将上述 Lua 测试脚本保存到 `benchmark/scripts/` 目录下。

### 5.3 执行性能测试
```bash
# 运行基准测试
cd benchmark
python benchmark_runner.py

# 生成分析报告
python analyze_results.py results/benchmark_results_YYYYMMDD_HHMMSS.json > performance_report.md
```

### 5.4 持续集成
```yaml
# .github/workflows/performance.yml
name: Performance Benchmark

on:
  push:
    branches: [ main, develop ]
  schedule:
    - cron: '0 2 * * 0'  # 每周日运行

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install Lua
      run: |
        sudo apt-get update
        sudo apt-get install -y lua5.4
    
    - name: Install Python dependencies
      run: |
        pip install psutil memory_profiler pytest
    
    - name: Run performance benchmarks
      run: |
        cd benchmark
        python benchmark_runner.py
    
    - name: Upload results
      uses: actions/upload-artifact@v3
      with:
        name: benchmark-results
        path: benchmark/results/
```

## 6. 性能优化指南

### 6.1 性能瓶颈识别
- **字节码执行**: 指令解释开销
- **函数调用**: 栈帧创建/销毁成本
- **内存管理**: Python 对象创建/垃圾回收
- **类型检查**: 动态类型系统开销

### 6.2 优化策略
1. **指令优化**: 减少冗余指令，合并常用操作
2. **缓存机制**: 缓存函数查找、常量访问
3. **内存池**: 复用对象，减少分配开销
4. **JIT 编译**: 热点代码编译为机器码（长期目标）

### 6.3 基准目标
- **基础操作**: 达到官方解释器 70% 以上性能
- **函数调用**: 达到官方解释器 60% 以上性能  
- **内存使用**: 控制在官方解释器 150% 以内
- **启动时间**: 控制在 100ms 以内

## 7. 扩展测试

### 7.1 真实应用场景测试
- **脚本执行**: 实际 Lua 脚本的性能表现
- **库调用**: 标准库函数的执行效率
- **协程切换**: 协程创建和切换的开销

### 7.2 压力测试
- **大数据集**: 处理大规模数据的性能
- **长时间运行**: 内存泄漏和性能退化检测
- **并发测试**: 多个解释器实例的资源竞争

### 7.3 回归测试
- **版本对比**: 不同版本间的性能回归检测
- **功能影响**: 新功能对现有性能的影响评估
- **优化验证**: 性能优化措施的效果验证

---

本文档将随着 haifa_lua 解释器的发展持续更新，为性能优化提供数据支持和改进方向。