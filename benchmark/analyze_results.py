#!/usr/bin/env python3
"""
性能测试结果分析与报告生成器
"""

import json
import sys
import statistics
from pathlib import Path
from typing import Dict, List

def load_results(results_file: str) -> Dict:
    """加载测试结果"""
    try:
        with open(results_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Results file '{results_file}' not found.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in results file: {e}")
        sys.exit(1)

def generate_performance_report(results: Dict) -> str:
    """生成性能分析报告"""
    report_lines = []
    
    # 标题
    report_lines.append("# Lua 解释器性能基准测试报告\n")
    
    # 测试环境信息
    test_info = results.get("test_info", {})
    report_lines.append("## 测试环境信息\n")
    report_lines.append(f"- **测试时间**: {test_info.get('timestamp', 'Unknown')}")
    report_lines.append(f"- **测试迭代**: {test_info.get('iterations', 'Unknown')} 次")
    
    if test_info.get('lua_version'):
        report_lines.append(f"- **Lua 版本**: {test_info.get('lua_version')}")
    else:
        report_lines.append("- **Lua 版本**: 未检测到官方 Lua 解释器")
    
    report_lines.append(f"- **Python 版本**: {test_info.get('python_version', 'Unknown')}")
    
    system_info = test_info.get('system_info', {})
    if system_info:
        report_lines.append(f"- **操作系统**: {system_info.get('platform', 'Unknown')}")
        report_lines.append(f"- **处理器**: {system_info.get('processor', 'Unknown')}")
    
    report_lines.append("")
    
    # 性能对比总览
    report_lines.append("## 性能对比总览\n")
    
    tests = results.get("tests", {})
    if not tests:
        report_lines.append("⚠️ 未找到测试结果数据。\n")
        return "\n".join(report_lines)
    
    # 创建对比表
    report_lines.append("| 测试项目 | Lua 官方 (秒) | haifa_lua (秒) | 性能比率 | 相对性能 |")
    report_lines.append("|----------|---------------|----------------|----------|----------|")
    
    ratios = []
    performances = []
    
    for test_name, test_data in tests.items():
        lua_data = test_data.get("lua_official", {})
        haifa_data = test_data.get("haifa_lua", {})
        
        lua_time = lua_data.get("avg_time", 0)
        haifa_time = haifa_data.get("avg_time", 0)
        ratio = test_data.get("performance_ratio", 0)
        rel_perf = test_data.get("relative_performance", 0)
        
        # 格式化显示
        lua_str = f"{lua_time:.4f}" if lua_time > 0 else "N/A"
        haifa_str = f"{haifa_time:.4f}" if haifa_time > 0 else "N/A"
        ratio_str = f"{ratio:.2f}x" if ratio > 0 else "N/A"
        perf_str = f"{rel_perf:.1f}%" if rel_perf > 0 else "N/A"
        
        # 简化测试名称显示
        display_name = test_name.replace("_bench.lua", "").replace("_", " ").title()
        
        report_lines.append(f"| {display_name} | {lua_str} | {haifa_str} | {ratio_str} | {perf_str} |")
        
        if ratio > 0:
            ratios.append(ratio)
            performances.append(rel_perf)
    
    # 计算总体性能
    if ratios:
        avg_ratio = statistics.mean(ratios)
        avg_performance = statistics.mean(performances)
        
        report_lines.append(f"| **平均值** | - | - | **{avg_ratio:.2f}x** | **{avg_performance:.1f}%** |")
        report_lines.append("")
        
        # 性能评估
        report_lines.append("### 总体性能评估\n")
        
        if avg_performance >= 70:
            level = "🟢 优秀"
            assessment = "haifa_lua 的性能表现优异，可以满足大部分生产环境需求。"
        elif avg_performance >= 50:
            level = "🟡 良好" 
            assessment = "haifa_lua 的性能表现良好，适合大多数应用场景，部分高性能场景可能需要优化。"
        elif avg_performance >= 30:
            level = "🟠 一般"
            assessment = "haifa_lua 的性能表现一般，建议在性能敏感的应用中谨慎使用，需要进一步优化。"
        else:
            level = "🔴 较差"
            assessment = "haifa_lua 的性能表现较差，不建议用于生产环境，需要大幅优化。"
        
        report_lines.append(f"**性能等级**: {level}")
        report_lines.append(f"**平均性能**: {avg_performance:.1f}% (相对于官方 Lua)")
        report_lines.append(f"**评估结论**: {assessment}")
        report_lines.append("")
    else:
        report_lines.append("\n⚠️ 无法计算性能比率，可能是由于测试执行失败。\n")
    
    # 详细测试结果
    report_lines.append("## 详细测试结果\n")
    
    for test_name, test_data in tests.items():
        display_name = test_name.replace("_bench.lua", "").replace("_", " ").title()
        report_lines.append(f"### {display_name}\n")
        
        # 测试完成情况
        iterations = test_data.get("iterations_completed", {})
        lua_completed = iterations.get("lua", 0)
        haifa_completed = iterations.get("haifa", 0)
        total_iterations = test_info.get("iterations", 0)
        
        report_lines.append(f"**测试完成情况**:")
        report_lines.append(f"- Lua 官方: {lua_completed}/{total_iterations} 次成功")
        report_lines.append(f"- haifa_lua: {haifa_completed}/{total_iterations} 次成功")
        report_lines.append("")
        
        # Lua 官方结果
        lua_data = test_data.get("lua_official", {})
        if lua_data:
            report_lines.append("**Lua 官方解释器结果**:")
            report_lines.append(f"- 平均执行时间: {lua_data.get('avg_time', 0):.4f} 秒")
            report_lines.append(f"- 最快时间: {lua_data.get('min_time', 0):.4f} 秒")
            report_lines.append(f"- 最慢时间: {lua_data.get('max_time', 0):.4f} 秒")
            
            std_dev = lua_data.get('std_dev', 0)
            if std_dev > 0:
                report_lines.append(f"- 标准差: {std_dev:.4f} 秒")
            
            # 显示样本输出（截取前200字符）
            sample_output = lua_data.get('sample_output', '').strip()
            if sample_output:
                lines = sample_output.split('\n')[:3]  # 显示前3行
                output_preview = '\n'.join(f"  {line}" for line in lines)
                report_lines.append(f"- 输出示例:\n```\n{output_preview}")
                if len(sample_output.split('\n')) > 3:
                    report_lines.append("  ...")
                report_lines.append("```")
            report_lines.append("")
        
        # haifa_lua 结果
        haifa_data = test_data.get("haifa_lua", {})
        if haifa_data:
            report_lines.append("**haifa_lua 解释器结果**:")
            report_lines.append(f"- 平均执行时间: {haifa_data.get('avg_time', 0):.4f} 秒")
            report_lines.append(f"- 最快时间: {haifa_data.get('min_time', 0):.4f} 秒")
            report_lines.append(f"- 最慢时间: {haifa_data.get('max_time', 0):.4f} 秒")
            
            std_dev = haifa_data.get('std_dev', 0)
            if std_dev > 0:
                report_lines.append(f"- 标准差: {std_dev:.4f} 秒")
            
            # 显示样本输出
            sample_output = haifa_data.get('sample_output', '').strip()
            if sample_output:
                lines = sample_output.split('\n')[:3]
                output_preview = '\n'.join(f"  {line}" for line in lines)
                report_lines.append(f"- 输出示例:\n```\n{output_preview}")
                if len(sample_output.split('\n')) > 3:
                    report_lines.append("  ...")
                report_lines.append("```")
            report_lines.append("")
        
        # 性能对比分析
        ratio = test_data.get("performance_ratio", 0)
        rel_perf = test_data.get("relative_performance", 0)
        
        if ratio > 0 and rel_perf > 0:
            report_lines.append("**性能分析**:")
            report_lines.append(f"- 性能比率: {ratio:.2f}x (haifa_lua 相对于 Lua 官方的倍数)")
            report_lines.append(f"- 相对性能: {rel_perf:.1f}% (haifa_lua 达到 Lua 官方的性能百分比)")
            
            if ratio < 2.0:
                analysis = "性能表现优异，接近官方解释器水平"
            elif ratio < 4.0:
                analysis = "性能表现良好，在可接受范围内"
            elif ratio < 8.0:
                analysis = "性能表现一般，有优化空间"
            else:
                analysis = "性能表现较差，需要重点优化"
            
            report_lines.append(f"- 评估: {analysis}")
            report_lines.append("")
        
        report_lines.append("---\n")
    
    # 优化建议
    if ratios:
        report_lines.append("## 性能优化建议\n")
        
        # 找出性能最差的测试
        worst_tests = []
        for test_name, test_data in tests.items():
            ratio = test_data.get("performance_ratio", 0)
            if ratio > 0:
                worst_tests.append((test_name, ratio))
        
        worst_tests.sort(key=lambda x: x[1], reverse=True)
        
        if worst_tests:
            report_lines.append("### 优先优化项目\n")
            for i, (test_name, ratio) in enumerate(worst_tests[:3]):
                display_name = test_name.replace("_bench.lua", "").replace("_", " ")
                report_lines.append(f"{i+1}. **{display_name}**: {ratio:.2f}x 倍性能差距")
        
        report_lines.append("\n### 通用优化策略\n")
        report_lines.append("1. **指令优化**: 减少字节码指令数量，优化常用操作路径")
        report_lines.append("2. **内存管理**: 优化对象分配和垃圾回收策略")  
        report_lines.append("3. **函数调用**: 减少函数调用开销，优化栈帧管理")
        report_lines.append("4. **缓存策略**: 缓存常用计算结果和查找操作")
        report_lines.append("5. **JIT 编译**: 考虑为热点代码实现即时编译")
        report_lines.append("")
    
    return "\n".join(report_lines)

def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("Usage: python analyze_results.py <results_file.json>")
        print("\nExample:")
        print("  python analyze_results.py benchmark/results/benchmark_results_20231225_143022.json")
        sys.exit(1)
    
    results_file = sys.argv[1]
    
    # 检查文件是否存在
    if not Path(results_file).exists():
        print(f"Error: File '{results_file}' not found.")
        
        # 提供帮助信息
        results_dir = Path("benchmark/results")
        if results_dir.exists():
            result_files = list(results_dir.glob("benchmark_results_*.json"))
            if result_files:
                print("\nAvailable result files:")
                for file in sorted(result_files, reverse=True)[:5]:
                    print(f"  {file}")
        sys.exit(1)
    
    print(f"Analyzing results from: {results_file}")
    
    # 加载并分析结果
    results = load_results(results_file)
    report = generate_performance_report(results)
    
    # 输出报告
    print("\n" + "="*80)
    print(report)
    
    # 保存报告到文件
    output_file = Path(results_file).with_suffix('.md')
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n{'='*80}")
    print(f"Report saved to: {output_file}")

if __name__ == "__main__":
    main()