# -*- coding: utf-8 -*-
"""
=============================================================================
脚本名称: regenerate_all.py
功能描述: 一键重新生成全流程分析结果。
         按顺序执行：情感重新打分 → 数据深度分析 → HTML 数据注入。
=============================================================================

【设计目的】
  在开发调试阶段，修改情感词典或分析参数后需要重新运行整个流程。
  手动依次执行三个脚本（step3 → enrich_data → update_html）繁琐易出错。
  本脚本通过 subprocess 串联这三个步骤，提供"一键重新生成"能力。

【执行流程】
  第 1 步：step3_analyze_aggregate.py
          → 使用混合情感评分（词典 55% + SnowNLP 45%）重新打分
          → 生成 LDA 主题模型、词云、统计图表
          → 输出 dashboard_data.json

  第 2 步：enrich_data.py
          → 对已打分数据进行 11 个维度的深度分析
          → 情感关键词类别、地理分布、时段模式、共现网络等
          → 输出 enriched_data.json

  第 3 步：update_html.py
          → 将两个 JSON 数据注入到 HTML 页面的内联 JS 变量中
          → 自动备份原文件为 .bak

【错误处理】
  每一步执行完毕后检查返回码，若非零则立即终止（sys.exit(1)），
  避免在前一步失败的脏数据上继续执行后续步骤。

【使用方法】
  cd code
  python regenerate_all.py

  【注意】此脚本不包含 step1（清洗）和 step2（分词），
         因为这两个步骤通常只需执行一次，数据不变时无需重跑。
=============================================================================
"""

import os
import sys
import subprocess

# ---- 脚本所在目录（所有子脚本都在同一目录下）----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(name: str, script: str):
    """
    运行单个处理步骤。

    【为什么用 subprocess 而非直接 import】
      - 每个脚本独立运行，有自己的 print 输出和错误处理逻辑
      - 避免模块级别的全局变量（如 jieba 词典、pandas 配置）互相干扰
      - 子进程失败时可以独立排查，不会污染当前进程的 Python 状态
      - 输出实时显示（capture_output=False），便于观察进度

    【参数说明】
      - sys.executable：当前 Python 解释器的完整路径，确保使用同一环境
      - cwd=SCRIPT_DIR：工作目录设为脚本所在目录，保证相对路径正确

    参数:
        name: 步骤名称（仅用于日志显示）
        script: 要执行的 Python 脚本文件名（相对于 SCRIPT_DIR）

    异常:
        sys.exit(1)：当子进程返回非零退出码时立即终止整个流程
    """
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")

    # ---- 启动子进程 ----
    # capture_output=False：子进程的输出直接流到终端，方便实时查看
    # 这样能看到进度条、分词进度等中间信息
    result = subprocess.run(
        [sys.executable, script],
        cwd=SCRIPT_DIR,
        capture_output=False
    )

    # ---- 检查执行结果 ----
    if result.returncode != 0:
        print(f"\n[FAILED] {name} (exit code {result.returncode})")
        print("  请检查上方错误信息后重试。")
        sys.exit(1)   # 非零退出码，通知外部调用者执行失败

    print(f"[OK] {name} completed.")


def main():
    """
    主流程：按依赖顺序依次执行三个步骤。

    步骤顺序不可更改：
      step3 生成 dashboard_data.json ← enrich_data.py 的输入依赖
      enrich_data.py 生成 enriched_data.json ← update_html.py 的输入依赖
    """
    # ---- 定义三步流水线 ----
    # 每个元组为 (显示名称, 脚本文件名)
    steps = [
        ("Step 1/3: Re-analyze sentiment (hybrid scoring)", "step3_analyze_aggregate.py"),
        ("Step 2/3: Re-enrich data (fixed category counting)", "enrich_data.py"),
        ("Step 3/3: Update HTML files with new JSON data", "update_html.py"),
    ]

    # ---- 打印运行环境信息 ----
    print("Pipeline: Sentiment Analysis Regeneration")
    print(f"Working directory: {SCRIPT_DIR}")
    print(f"Python: {sys.executable}")

    # ---- 依次执行各步骤 ----
    for name, script in steps:
        run_step(name, script)

    # ---- 完成提示 ----
    print(f"\n{'=' * 60}")
    print("  [SUCCESS] All steps completed!")
    print(f"{'=' * 60}")
    print("\nNext: Open 3/index_trial.html in a browser to view results.")


if __name__ == "__main__":
    main()
