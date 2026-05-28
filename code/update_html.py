# -*- coding: utf-8 -*-
"""
=============================================================================
脚本名称: update_html.py
功能描述: 将重新生成的 JSON 数据注入到 HTML 可视化页面中，
         替换内联的 JavaScript 变量声明。
=============================================================================

【背景】
  前端 HTML 页面（index_trial.html 等）使用 ECharts 进行可视化展示。
  数据以 JavaScript 内联变量的形式嵌入 HTML 文件中：
    - `var dashboardData = {...};`  包含仪表盘统计数据
    - `var enrichedData = {...};`   包含深度分析数据

  当后端 Python 脚本重新生成分析结果（dashboard_data.json / enriched_data.json）后，
  需要将这些 JSON 数据同步更新到 HTML 文件中，而无需手动复制粘贴。

【工作原理】
  1. 读取最新的 dashboard_data.json 和 enriched_data.json
  2. 使用正则表达式在 HTML 文件中定位两个变量声明
  3. 用新的 JSON 内容替换旧的变量值
  4. 每次修改前自动备份原文件（.bak 后缀）

【正则表达式策略】
  使用 re.DOTALL 标志使 . 匹配换行符，配合非贪婪量词 *?
  精确匹配 `var xxx = {...};` 的结构，只替换第一个匹配项（count=1）。

【输入】dashboard_data.json、enriched_data.json
【输出】更新后的 HTML 文件（原文件备份为 .bak）
=============================================================================
"""

import json
import re
import os
import shutil

# ---- 基于脚本所在目录定位所有文件 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 需要更新的 HTML 文件列表 ----
# 三个文件分别对应：主页面、备用页面、最终设计页面
HTML_FILES = [
    os.path.join(SCRIPT_DIR, "3", "index_trial.html"),
    os.path.join(SCRIPT_DIR, "3", "index.html"),
    os.path.join(SCRIPT_DIR, "3", "final design", "index.html"),
]

# ---- JSON 数据源文件路径 ----
DASHBOARD_JSON = os.path.join(SCRIPT_DIR, "dashboard_data.json")
ENRICHED_JSON = os.path.join(SCRIPT_DIR, "enriched_data.json")


def update_html(filepath: str, dashboard_json_str: str, enriched_json_str: str):
    """
    更新单个 HTML 文件中的内联 JSON 数据。

    【处理流程】
      1. 检查文件是否存在，不存在则跳过
      2. 读取 HTML 文件全部内容
      3. 用正则替换 `var dashboardData = {...};` 块
      4. 用正则替换 `var enrichedData = {...};` 块
      5. 如果内容有变化：先备份再写入，无变化则跳过

    【安全机制】
      - 修改前自动创建 .bak 备份文件（使用 shutil.copy2 保留元数据）
      - 使用 count=1 确保只替换第一个匹配（避免误替换其他变量的同名赋值）
      - re.DOTALL 标志使 . 能匹配换行符，确保能捕获多行 JSON

    参数:
        filepath: HTML 文件的完整路径
        dashboard_json_str: dashboard_data.json 的原始 JSON 字符串
        enriched_json_str: enriched_data.json 的原始 JSON 字符串
    """
    if not os.path.exists(filepath):
        print(f"  [SKIP] Not found: {filepath}")
        return

    # ---- 步骤 1：读取 HTML 文件 ----
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # ---- 步骤 2：替换 dashboardData 变量 ----
    # 正则说明：
    #   var dashboardData =    → 匹配变量声明开头
    #   \{.*?\};               → 非贪婪匹配花括号内的 JSON 内容（含换行）
    #   re.DOTALL              → . 可以匹配 \n，因为 JSON 通常是多行的
    #   count=1                → 只替换第一个匹配项，安全上限
    new_content = re.sub(
        r'var dashboardData = \{.*?\};',
        f'var dashboardData = {dashboard_json_str};',
        content, count=1, flags=re.DOTALL
    )

    # ---- 步骤 3：替换 enrichedData 变量 ----
    new_content = re.sub(
        r'var enrichedData = \{.*?\};',
        f'var enrichedData = {enriched_json_str};',
        new_content, count=1, flags=re.DOTALL
    )

    # ---- 步骤 4：检查是否有实际变化 ----
    # 如果新旧内容完全一致，说明 JSON 数据未变化，跳过更新
    if new_content == content:
        print(f"  [UNCHANGED] {filepath}")
        return

    # ---- 步骤 5：备份原文件 ----
    # shutil.copy2 会保留文件的修改时间和元数据
    backup = filepath + ".bak"
    shutil.copy2(filepath, backup)

    # ---- 步骤 6：写入新内容 ----
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  [UPDATED] {filepath} (backup: {backup})")


def main():
    """
    主流程：加载 JSON 数据 → 逐个更新 HTML 文件。
    """
    # ---- 加载 JSON 数据源 ----
    # 直接读取为字符串（而非解析为 dict），保持原始 JSON 格式
    # 这样注入到 JS 变量时语法完全一致
    with open(DASHBOARD_JSON, "r", encoding="utf-8") as f:
        dashboard_json = f.read().strip()

    with open(ENRICHED_JSON, "r", encoding="utf-8") as f:
        enriched_json = f.read().strip()

    # ---- 打印基本信息供确认 ----
    print(f"Dashboard JSON size: {len(dashboard_json):,} chars")
    print(f"Enriched JSON size:  {len(enriched_json):,} chars")
    print()

    # ---- 逐个更新目标 HTML 文件 ----
    for html_file in HTML_FILES:
        update_html(html_file, dashboard_json, enriched_json)

    print("\n[Done] HTML files updated.")


if __name__ == "__main__":
    main()
