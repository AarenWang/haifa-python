#!/usr/bin/env python3
"""
Lua 解释器性能基准测试执行器
用于对比 Lua 官方解释器和 haifa_lua 的性能
"""

import os
import sys
import time
import subprocess
import json
import psutil
import statistics
from pathlib import Path
from typing import Dict, List, Tuple, Optional

class LuaBenchmarkRunner:
    def __init__(self, benchmark_dir: str = "benchmark"):
        self.benchmark_dir = Path(benchmark_dir)
        self.results_dir = self.benchmark_dir / "results" 
        self.scripts_dir = self.benchmark_dir / "scripts"
        
        # 确保目录存在
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.scripts_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查解释器可用性
        self.check_interpreters()
    
    def check_interpreters(self):
        """检查解释器是否可用"""
        # 检查官方 Lua
        try:
            result = subprocess.run(['lua', '-v'], capture_output=True, text=True)
            if result.returncode == 0:
                self.lua_version = result.stderr.strip() or result.stdout.strip()
                print(f"Found Lua: {self.lua_version}")
            else:
                print("Warning: Official Lua interpreter not found!")
                self.lua_version = None
        except FileNotFoundError:
            print("Warning: Official Lua interpreter not found!")
            self.lua_version = None
        
        # 检查 haifa_lua
        try:
            # 检查是否在正确的项目目录
            if not (Path.cwd() / "haifa_lua").exists():
                print("Warning: haifa_lua module not found in current directory!")
                print("Please run this script from the haifa-python project root.")
            self.haifa_available = True
        except Exception as e:
            print(f"Warning: haifa_lua not available: {e}")
            self.haifa_available = False
    
    def run_lua_official(self, script_path: str) -> Tuple[float, str, Dict]:
        """运行官方 Lua 解释器"""
        if not self.lua_version:
            return 0, "", {"error": "Lua not available"}
        
        start_time = time.perf_counter()
        
        try:
            result = subprocess.run(
                ['lua', str(script_path)],
                capture_output=True,
                text=True,
                timeout=60  # 60秒超时
            )
            
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            
            return execution_time, result.stdout, {
                "stderr": result.stderr,
                "return_code": result.returncode,
                "timeout": False
            }
            
        except subprocess.TimeoutExpired:
            return 60.0, "", {"error": "Timeout", "timeout": True}
        except Exception as e:
            return 0, "", {"error": str(e)}
    
    def run_haifa_lua(self, script_path: str) -> Tuple[float, str, Dict]:
        """运行 haifa_lua 解释器"""
        if not self.haifa_available:
            return 0, "", {"error": "haifa_lua not available"}
        
        start_time = time.perf_counter()
        
        try:
            # 使用 haifa_lua 的 runtime 模块直接执行
            script_content = Path(script_path).read_text(encoding='utf-8')
            
            # 导入并执行
            sys.path.insert(0, str(Path.cwd()))
            from haifa_lua.runtime import run_source
            
            # 捕获输出
            from io import StringIO
            import contextlib
            
            old_stdout = sys.stdout
            sys.stdout = mystdout = StringIO()
            
            try:
                result = run_source(script_content, load_stdlib=True)
                output = mystdout.getvalue()
                
                # 如果没有输出但有结果，添加结果到输出
                if not output and result:
                    output = '\n'.join(str(r) for r in result) + '\n'
                
            finally:
                sys.stdout = old_stdout
            
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            
            return execution_time, output, {
                "return_code": 0,
                "timeout": False
            }
            
        except Exception as e:
            end_time = time.perf_counter()
            execution_time = end_time - start_time
            
            # 获取详细的错误信息
            import traceback
            error_details = traceback.format_exc()
            
            return execution_time, "", {
                "error": str(e),
                "error_details": error_details,
                "return_code": 1
            }
    
    def run_benchmark_suite(self, iterations: int = 3) -> Dict:
        """运行完整的基准测试套件"""
        # 原始脚本用于官方Lua，haifa兼容脚本用于haifa_lua
        test_scripts = [
            ("arithmetic_bench.lua", "arithmetic_haifa.lua"),
            ("function_bench.lua", "function_haifa.lua"), 
            ("control_bench.lua", "control_haifa.lua")
        ]
        
        results = {
            "test_info": {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "iterations": iterations,
                "python_version": sys.version,
                "lua_version": self.lua_version,
                "system_info": {
                    "platform": sys.platform,
                    "processor": os.uname().machine if hasattr(os, 'uname') else 'unknown'
                }
            },
            "tests": {}
        }
        
        for script_pair in test_scripts:
            if isinstance(script_pair, tuple):
                lua_script, haifa_script = script_pair
            else:
                # 向后兼容单个脚本
                lua_script = haifa_script = script_pair
            
            lua_script_path = self.scripts_dir / lua_script
            haifa_script_path = self.scripts_dir / haifa_script
            
            print(f"\nRunning {lua_script} vs {haifa_script}...")
            
            # 运行多次取平均值
            lua_times = []
            haifa_times = []
            lua_outputs = []
            haifa_outputs = []
            
            for i in range(iterations):
                print(f"  Iteration {i+1}/{iterations}")
                
                # 官方 Lua
                if self.lua_version and lua_script_path.exists():
                    try:
                        exec_time, output, stats = self.run_lua_official(str(lua_script_path))
                        if not stats.get("timeout") and stats.get("return_code") == 0:
                            lua_times.append(exec_time)
                            lua_outputs.append(output)
                        else:
                            print(f"    Lua official failed: {stats}")
                    except Exception as e:
                        print(f"    Lua official error: {e}")
                
                # haifa_lua
                if self.haifa_available and haifa_script_path.exists():
                    try:
                        exec_time, output, stats = self.run_haifa_lua(str(haifa_script_path))
                        if stats.get("return_code") == 0:
                            haifa_times.append(exec_time)
                            haifa_outputs.append(output)
                        else:
                            print(f"    haifa_lua failed: {stats}")
                    except Exception as e:
                        print(f"    haifa_lua error: {e}")
                
                time.sleep(0.1)  # 短暂冷却
            
            # 计算统计结果
            test_result = {
                "script_name": f"{lua_script} vs {haifa_script}",
                "lua_script": lua_script,
                "haifa_script": haifa_script,
                "iterations_completed": {
                    "lua": len(lua_times),
                    "haifa": len(haifa_times)
                }
            }
            
            if lua_times:
                test_result["lua_official"] = {
                    "times": lua_times,
                    "avg_time": statistics.mean(lua_times),
                    "min_time": min(lua_times),
                    "max_time": max(lua_times),
                    "std_dev": statistics.stdev(lua_times) if len(lua_times) > 1 else 0,
                    "sample_output": lua_outputs[0] if lua_outputs else ""
                }
            
            if haifa_times:
                test_result["haifa_lua"] = {
                    "times": haifa_times,
                    "avg_time": statistics.mean(haifa_times),
                    "min_time": min(haifa_times),
                    "max_time": max(haifa_times),
                    "std_dev": statistics.stdev(haifa_times) if len(haifa_times) > 1 else 0,
                    "sample_output": haifa_outputs[0] if haifa_outputs else ""
                }
            
            # 计算性能比率
            if lua_times and haifa_times:
                lua_avg = statistics.mean(lua_times)
                haifa_avg = statistics.mean(haifa_times)
                if lua_avg > 0:
                    test_result["performance_ratio"] = haifa_avg / lua_avg
                    test_result["relative_performance"] = (lua_avg / haifa_avg) * 100
            
            results["tests"][lua_script] = test_result
        
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
    
    def print_summary(self, results: Dict):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("="*60)
        
        test_info = results.get("test_info", {})
        print(f"Test Time: {test_info.get('timestamp')}")
        print(f"Iterations: {test_info.get('iterations')}")
        print(f"Lua Version: {test_info.get('lua_version', 'Not available')}")
        print()
        
        total_ratio = 0
        ratio_count = 0
        
        print(f"{'Test':<20} {'Lua (s)':<12} {'haifa_lua (s)':<15} {'Ratio':<8} {'Performance':<12}")
        print("-" * 75)
        
        for test_name, test_data in results.get("tests", {}).items():
            lua_time = test_data.get("lua_official", {}).get("avg_time", 0)
            haifa_time = test_data.get("haifa_lua", {}).get("avg_time", 0)
            ratio = test_data.get("performance_ratio", 0)
            rel_perf = test_data.get("relative_performance", 0)
            
            lua_str = f"{lua_time:.4f}" if lua_time > 0 else "N/A"
            haifa_str = f"{haifa_time:.4f}" if haifa_time > 0 else "N/A"
            ratio_str = f"{ratio:.2f}x" if ratio > 0 else "N/A"
            perf_str = f"{rel_perf:.1f}%" if rel_perf > 0 else "N/A"
            
            print(f"{test_name:<20} {lua_str:<12} {haifa_str:<15} {ratio_str:<8} {perf_str:<12}")
            
            if ratio > 0:
                total_ratio += ratio
                ratio_count += 1
        
        if ratio_count > 0:
            avg_ratio = total_ratio / ratio_count
            avg_performance = (1 / avg_ratio) * 100
            print("-" * 75)
            print(f"{'AVERAGE':<20} {'':<12} {'':<15} {avg_ratio:.2f}x{'':<4} {avg_performance:.1f}%")
            
            print(f"\nOverall Assessment:")
            if avg_performance >= 70:
                assessment = "Excellent - Very competitive performance"
            elif avg_performance >= 50:
                assessment = "Good - Acceptable performance for most use cases" 
            elif avg_performance >= 30:
                assessment = "Fair - Needs optimization for production use"
            else:
                assessment = "Poor - Significant optimization required"
            
            print(f"  {assessment}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Lua 解释器性能基准测试')
    parser.add_argument('-i', '--iterations', type=int, default=3,
                       help='测试迭代次数 (default: 3)')
    parser.add_argument('-o', '--output', type=str,
                       help='结果输出文件名')
    parser.add_argument('--benchmark-dir', type=str, default='benchmark',
                       help='基准测试目录 (default: benchmark)')
    
    args = parser.parse_args()
    
    # 检查是否在正确目录
    if not Path('haifa_lua').exists():
        print("Error: Please run this script from the haifa-python project root directory.")
        print("Expected to find 'haifa_lua' module in current directory.")
        sys.exit(1)
    
    runner = LuaBenchmarkRunner(args.benchmark_dir)
    
    print("Starting Lua interpreter performance benchmark...")
    print(f"Iterations per test: {args.iterations}")
    print()
    
    results = runner.run_benchmark_suite(iterations=args.iterations)
    result_path = runner.save_results(results, args.output)
    runner.print_summary(results)
    
    print(f"\nDetailed results saved to: {result_path}")
    print("Run 'python benchmark/analyze_results.py <result_file>' for detailed analysis.")

if __name__ == "__main__":
    main()