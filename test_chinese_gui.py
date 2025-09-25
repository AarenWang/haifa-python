#!/usr/bin/env python3
"""
测试 GUI 可视化器中文显示功能
Test Chinese display in GUI visualizer
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_chinese_display():
    """测试中文字体加载和显示"""
    try:
        import pygame
        pygame.init()
        
        from compiler.vm_visualizer import _get_chinese_font
        
        print("测试中文字体加载...")
        font = _get_chinese_font(18)
        
        # 测试渲染中英文混合文本
        test_texts = [
            "Hello World",
            "你好世界",
            "测试 Test 中英文混合",
            "函数 function 变量 variable",
            "数字：42 中文数字：四十二"
        ]
        
        print("测试文本渲染:")
        for text in test_texts:
            try:
                surface = font.render(text, True, (0, 0, 0))
                width = surface.get_width()
                print(f"  ✓ '{text}' -> 宽度: {width}px")
            except Exception as e:
                print(f"  ✗ '{text}' -> 错误: {e}")
        
        pygame.quit()
        print("中文字体测试完成！")
        
    except ImportError as e:
        print(f"pygame 未安装: {e}")
        print("请运行: pip install \".[gui]\"")
        raise
    except Exception as e:
        print(f"测试失败: {e}")
        raise

if __name__ == "__main__":
    test_chinese_display()