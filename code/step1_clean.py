# -*- coding: utf-8 -*-
"""
=============================================================================
脚本名称: step1_clean.py
功能描述: 网易云音乐评论数据清洗
         容错读取 → 去重 → 长度过滤 → 内容清洗 → 统计输出 → 结果导出
=============================================================================

本脚本是数据处理流水线的第一步，负责将原始爬取的评论数据清洗为干净的结构化数据。

【处理流程】
  1. 自动检测文件编码 —— 解决中文 Windows / 服务器编码不一致问题
  2. Comment_ID 去重 —— 同一评论可能因 API 翻页重复出现
  3. Content 内容去重 —— 去除复制粘贴的重复评论
  4. 文本长度过滤 —— 过短无意义（<3字）、过长可能是广告或异常数据（>800字）
  5. 内容质量过滤 —— 纯 Emoji / 纯标点 / 重复符号 / 引流推广
  6. 清理保留内容中的 Emoji 符号，保留纯文字
  7. 输出清洗统计报告到 cleaning_stats.txt

【输入】netease_comments_1890530891_checkpoint.csv（原始爬取的评论数据）
【输出】comments_cleaned.csv（清洗后的数据）、cleaning_stats.txt（统计报告）
=============================================================================
"""

import os
import re
import pandas as pd
import numpy as np
from typing import Tuple


# ======================================================================
# 第一部分：全局配置常量
# ======================================================================

# ---- 文件路径配置 ----
# 所有路径均基于脚本所在目录计算，确保可在任意位置运行
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))  # 获取脚本所在目录的绝对路径
INPUT_FILE = os.path.join(SCRIPT_DIR, "netease_comments_1890530891_checkpoint.csv")  # 原始爬取数据
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "comments_cleaned.csv")  # 清洗后输出文件
STATS_FILE = os.path.join(SCRIPT_DIR, "cleaning_stats.txt")  # 清洗统计报告

# ---- 编码检测顺序 ----
# 按实际使用概率从高到低排列，依次尝试直到读取成功
# utf-8：现代化标准编码
# gb18030/gbk：中文 Windows 系统常用编码
# utf-8-sig：带 BOM 头的 UTF-8
# latin1：兜底方案（几乎不会失败，但中文会乱码）
ENCODINGS = ["utf-8", "gb18030", "gbk", "utf-8-sig", "latin1"]

# ---- 文本长度阈值 ----
# MIN_TEXT_LEN = 3：过短的评论（如 "好听"、"dd"）通常缺乏分析价值
# MAX_TEXT_LEN = 800：过长的评论可能是广告文案、小说片段或异常数据
MIN_TEXT_LEN = 3
MAX_TEXT_LEN = 800

# ======================================================================
# 第二部分：正则表达式模块（预编译，提升大批量匹配性能）
# ======================================================================

# ---- Emoji 匹配正则 ----
# 覆盖了常见的 Unicode Emoji 范围：表情符号、交通标志、国旗、符号扩展等
# 注意：各 Unicode 范围必须独立列出，不可使用跨平面范围（如 \U000024C2-\U0001F251），
# 否则会匹配 BMP（基本多文种平面）到 SMP（补充多文种平面）之间的全部字符，误伤中文等正常文本
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"    # Emoticons（笑脸、手势等表情符号）
    "\U0001F300-\U0001F5FF"    # Miscellaneous Symbols & Pictographs（天气、植物、食物等）
    "\U0001F680-\U0001F6FF"    # Transport & Map Symbols（交通工具、地图符号）
    "\U0001F1E0-\U0001F1FF"    # Regional Indicator Symbols（国旗字母组合，如 🇨🇳）
    "\U0001F900-\U0001F9FF"    # Supplemental Symbols & Pictographs（补充表情符号）
    "\U0001FA00-\U0001FA6F"    # Chess Symbols（象棋符号）
    "\U0001FA70-\U0001FAFF"    # Symbols Extended-A（符号扩展 A 区）
    "\U00002600-\U000027BF"    # Miscellaneous Symbols + Dingbats（杂项符号 + 装饰符号）
    "\U00002300-\U000023FF"    # Miscellaneous Technical（杂项技术符号）
    "\U00002B50"               # ⭐ 星号
    "\U00002764"               # ❤ 心形
    "\U00002702"               # ✂ 剪刀
    "\U000024C2"               # Ⓜ 圆圈 M
    "\U0001F250-\U0001F251"   # Enclosed Ideographic Supplement（带圈表意文字）
    "\U0000200D"               # Zero Width Joiner（零宽连接符，用于组合 emoji）
    "\U0000FE0F"               # Variation Selector-16（变体选择符，控制 emoji 样式）
    "\U000000A9"               # © 版权符号
    "\U000000AE"               # ® 注册商标符号
    "\U00002022-\U00002033"   # 角标数字（• 等）
    "]+",
    flags=re.UNICODE,
)

# ---- 纯标点符号匹配正则 ----
# 匹配只包含中英文常见标点符号（含空格）的评论
# 例如："。。。。"，"！！！？？"，"... ..."
PUNCT_PATTERN = re.compile(
    r"^[\s，。！？、；：""''（）《》【】…—～·,.!?;:'\"()\[\]{}|\\/`~@#$%^&*+=<>_-]+$"
)

# ---- 连续重复符号匹配正则 ----
# 匹配 3 次及以上连续重复的无意义符号
# 例如："。。。。。。"，"？？？？？"，"～～～～"
REPEATED_SYMBOL_PATTERN = re.compile(
    r"^[。！？～…\.\!\?\~]{3,}$"
)

# ---- 引流 / 推广关键词列表 ----
# 网易云评论区常见的广告、刷粉、引流等垃圾内容关键词
# 大小写不敏感匹配
PROMOTION_KEYWORDS = [
    "加微信", "加V", "加v", "扫码", "关注公众号", "私信我", "免费领",
    "点击链接", "下载APP", "加群", "QQ群", "微信群", "互粉", "互关",
    "刷粉", "代刷", "低价", "优惠券", "复制口令", "打开淘宝",
    "招代理", "兼职", "日结", "私聊", "加我", "看我主页",
    "VX", "vx", "Vx", "WX", "wx", "扣扣", "企鹅",
]


# ======================================================================
# 第三部分：内容质量判断函数
# ======================================================================

def is_pure_emoji(text: str) -> bool:
    """
    判断文本去除所有 Emoji 后是否为空（即评论仅由 Emoji 组成）。

    示例:
        '🎵🎵🎵❤️' → True  （纯 emoji，无文字）
        '好听🎵'    → False （有文字内容）
    """
    stripped = EMOJI_PATTERN.sub("", text).strip()  # 用正则移除所有 emoji
    return len(stripped) == 0


def is_pure_punctuation(text: str) -> bool:
    """
    判断文本是否仅由标点符号组成。

    示例:
        '。。。'    → True
        '好听。。。' → False
    """
    return bool(PUNCT_PATTERN.match(text))


def is_repeated_symbols(text: str) -> bool:
    """
    判断文本是否为连续无意义重复符号。

    示例:
        '。。。。。。' → True
        '？？？？'    → True
        '好听？？'    → False
    """
    return bool(REPEATED_SYMBOL_PATTERN.match(text))


def has_promotion_keywords(text: str) -> bool:
    """
    检查文本是否包含任何引流 / 推广关键词。
    使用大小写不敏感的匹配方式。

    示例:
        '加微信 xxx 了解'  → True
        '这首歌真好听'      → False
    """
    text_lower = text.lower()
    for kw in PROMOTION_KEYWORDS:
        if kw.lower() in text_lower:
            return True
    return False


def clean_text(text: str) -> str:
    """
    清除文本中的 Emoji 表情符号，保留纯文字内容。

    示例:
        '好听🎵太好听了❤️' → '好听太好听了'
    """
    return EMOJI_PATTERN.sub("", text).strip()


# ======================================================================
# 第四部分：数据读取模块
# ======================================================================

def detect_encoding(filepath: str) -> str:
    """
    自动检测 CSV 文件的字符编码。

    依次尝试预设的编码列表（utf-8 → gb18030 → gbk → utf-8-sig → latin1），
    逐个读取文件前 10 行验证，第一个解码成功的就是正确编码。
    若全部失败，使用 latin1 兜底（几乎不会解码失败，但中文会乱码）。

    参数:
        filepath: CSV 文件的完整路径

    返回:
        str: 检测到的编码名称
    """
    for enc in ENCODINGS:
        try:
            # 尝试读取前 10 行验证该编码是否有效
            with open(filepath, "r", encoding=enc) as f:
                for _ in range(10):
                    f.readline()
            return enc  # 读取成功，返回当前编码
        except (UnicodeDecodeError, UnicodeError):
            continue  # 解码失败，尝试下一个编码

    # 所有预设编码均失败时的兜底方案
    print("[WARN] 所有预设编码均失败，使用 latin1 兜底读取，请检查数据质量。")
    return "latin1"


def load_data(filepath: str) -> pd.DataFrame:
    """
    容错读取 CSV 文件。

    功能:
      - 调用 detect_encoding() 自动检测文件编码
      - 强制将 ID 类字段（Comment_ID / User_ID / Replied_User_ID）读取为字符串，
        防止科学计数法显示（如 1.89E+9）
      - 使用 low_memory=False 避免 pandas 分块读取时的类型推断警告

    参数:
        filepath: CSV 文件路径

    返回:
        pd.DataFrame: 加载完成的数据表
    """
    encoding = detect_encoding(filepath)
    print(f"[INFO] 检测到文件编码: {encoding}")

    # 指定 ID 类字段为字符串类型，防止被解析为数值
    dtype_spec = {
        "Comment_ID": str,
        "User_ID": str,
        "Replied_User_ID": str,
    }

    df = pd.read_csv(
        filepath,
        encoding=encoding,
        dtype=dtype_spec,
        low_memory=False,
    )
    return df


# ======================================================================
# 第五部分：数据清洗模块（按顺序执行）
# ======================================================================

def remove_invalid_ids(df: pd.DataFrame) -> pd.DataFrame:
    """
    第一步清洗：去除 Comment_ID 缺失或重复的记录。

    - 缺失处理：移除 Comment_ID 为 NaN 或空字符串的行（API 异常导致的数据残缺）
    - 重复处理：API 翻页时可能拉取到重复数据，保留首次出现的记录

    参数:
        df: 原始 DataFrame

    返回:
        pd.DataFrame: ID 去重后的 DataFrame
    """
    before = len(df)

    # 去除 Comment_ID 为空（NaN 或空字符串）的记录
    df = df.dropna(subset=["Comment_ID"])
    df = df[df["Comment_ID"].str.strip() != ""]

    # 按 Comment_ID 去重，保留首次出现
    df = df.drop_duplicates(subset=["Comment_ID"], keep="first")

    after = len(df)
    print(f"  [去重ID] {before} → {after} (去除 {before - after} 条)")
    return df


def remove_duplicate_content(df: pd.DataFrame) -> pd.DataFrame:
    """
    第二步清洗：去除 Content 内容完全重复的记录。

    原因：评论区常见复制粘贴刷屏行为（如歌词接龙、口号式刷屏），
    内容完全相同的评论只保留首条，其余视为垃圾数据。

    参数:
        df: 当前 DataFrame

    返回:
        pd.DataFrame: 内容去重后的 DataFrame
    """
    before = len(df)

    # 先去除 Content 为空的行，再按内容去重
    df = df.dropna(subset=["Content"])
    df = df.drop_duplicates(subset=["Content"], keep="first")

    after = len(df)
    print(f"  [去重内容] {before} → {after} (去除 {before - after} 条)")
    return df


def filter_by_text_length(df: pd.DataFrame) -> pd.DataFrame:
    """
    第三步清洗：按文本长度过滤评论。

    逻辑:
      - 优先使用原始数据中的 Text_Length 列（若存在且有效）
      - 同时计算 Content 的实际字符长度作为参考
      - 取两者中的较大值作为判定长度，避免因 Text_Length 字段记录错误而误删
      - 过滤掉小于 MIN_TEXT_LEN（3字）或大于 MAX_TEXT_LEN（800字）的记录

    参数:
        df: 当前 DataFrame

    返回:
        pd.DataFrame: 长度过滤后的 DataFrame
    """
    before = len(df)

    # 计算 Content 的实际字符长度（Python 原生 len 对中文也按字计数）
    actual_len = df["Content"].astype(str).str.len()

    # 若原始数据有 Text_Length 列，取它与实际长度的较大值
    if "Text_Length" in df.columns:
        text_len_col = pd.to_numeric(df["Text_Length"], errors="coerce").fillna(0).astype(int)
        effective_len = np.maximum(actual_len, text_len_col)  # 逐元素取最大值
    else:
        effective_len = actual_len

    # 应用长度区间过滤
    mask = (effective_len >= MIN_TEXT_LEN) & (effective_len <= MAX_TEXT_LEN)
    df = df[mask].copy()  # 使用 .copy() 避免后续操作的 SettingWithCopyWarning

    after = len(df)
    print(f"  [长度过滤] {before} → {after} (去除 {before - after} 条, "
          f"范围: {MIN_TEXT_LEN}~{MAX_TEXT_LEN} 字符)")
    return df


def filter_by_content_quality(df: pd.DataFrame) -> pd.DataFrame:
    """
    第四步清洗：内容质量过滤。

    剔除以下四类无效评论:
      1. 纯 Emoji 表情 —— 如 '🎵🎵❤️'（无任何文字信息）
      2. 纯标点符号   —— 如 '。。。'、'！！！'（无意义刷屏）
      3. 连续重复符号 —— 如 '？？？？？'（灌水行为）
      4. 引流推广内容 —— 如 '加微信 xxx 了解'（广告 / 诈骗）

    同时，对保留的有效评论，清除其中嵌入的 Emoji 符号，使文本更干净。

    参数:
        df: 当前 DataFrame

    返回:
        pd.DataFrame: 质量过滤后的 DataFrame
    """
    before = len(df)

    contents = df["Content"].astype(str)

    # 逐条检测四类无效内容，返回布尔掩码
    mask_emoji = contents.apply(is_pure_emoji)            # 纯 Emoji
    mask_punct = contents.apply(is_pure_punctuation)       # 纯标点
    mask_repeat = contents.apply(is_repeated_symbols)      # 重复符号
    mask_promo = contents.apply(has_promotion_keywords)    # 引流推广

    # 合并所有无效标记（任一为 True 即过滤掉）
    bad_mask = mask_emoji | mask_punct | mask_repeat | mask_promo

    df = df[~bad_mask].copy()  # 取反：保留非无效的评论

    after = len(df)
    print(f"  [内容清洗] {before} → {after} (去除 {before - after} 条)")
    print(f"    - 纯Emoji: {mask_emoji.sum()}")
    print(f"    - 纯标点:  {mask_punct.sum()}")
    print(f"    - 重复符号: {mask_repeat.sum()}")
    print(f"    - 引流推广: {mask_promo.sum()}")

    # 对保留的内容，清除其中嵌入的 Emoji，使文本更纯净
    df["Content"] = df["Content"].astype(str).apply(clean_text)

    return df


# ======================================================================
# 第六部分：统计输出模块
# ======================================================================

def save_statistics(
    raw_count: int,
    after_id_dedup: int,
    after_content_dedup: int,
    after_len_count: int,
    final_count: int,
    output_path: str,
) -> None:
    """
    打印并保存清洗统计信息到文件。

    记录每一步的数据量变化、保留率和总去除率，
    同时输出到控制台和 cleaning_stats.txt 文件。

    参数:
        raw_count:           原始数据总量
        after_id_dedup:      ID 去重后的数量
        after_content_dedup: 内容去重后的数量
        after_len_count:     长度过滤后的数量
        final_count:         最终保留数据量
        output_path:         统计报告输出文件路径
    """
    lines = [
        "=" * 50,
        "         网易云评论数据清洗统计报告",
        "=" * 50,
        f"原始数据量:          {raw_count:>8,} 条",
        f"ID去重后:            {after_id_dedup:>8,} 条  ({after_id_dedup / raw_count * 100:.2f}%)",
        f"内容去重后:          {after_content_dedup:>8,} 条  ({after_content_dedup / raw_count * 100:.2f}%)",
        f"长度过滤后:          {after_len_count:>8,} 条  ({after_len_count / raw_count * 100:.2f}%)",
        f"最终保留数据量:       {final_count:>8,} 条  ({final_count / raw_count * 100:.2f}%)",
        "-" * 50,
        f"总去除量:            {raw_count - final_count:>8,} 条  ({(raw_count - final_count) / raw_count * 100:.2f}%)",
        "=" * 50,
    ]

    report = "\n".join(lines)

    # 输出到控制台
    print("\n" + report)

    # 保存到文件（UTF-8 编码，Windows 记事本可直接打开）
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n[INFO] 统计报告已保存至: {output_path}")


# ======================================================================
# 第七部分：主流程入口
# ======================================================================

def main() -> None:
    """
    数据清洗主流程，按顺序执行七个步骤。

    Step 1: 加载原始数据 —— 自动检测编码并读取 CSV
    Step 2: Comment_ID 去重 —— 去除同一 ID 的重复抓取
    Step 3: Content 内容去重 —— 去除复制粘贴的完全重复评论
    Step 4: 文本长度过滤 —— 保留 3~800 字的评论
    Step 5: 内容质量清洗 —— 过滤 Emoji / 标点 / 重复符号 / 引流词
    Step 6: 生成统计报告 —— 输出清洗前后数据量对比
    Step 7: 导出清洗后数据 —— 保存为 comments_cleaned.csv
    """

    # ---- Step 1: 加载原始数据 ----
    print("[STEP 1] 加载原始数据...")
    df = load_data(INPUT_FILE)
    raw_count = len(df)
    print(f"  原始数据量: {raw_count:,} 条\n")

    # ---- Step 2: ID 去重 ----
    print("[STEP 2] Comment_ID 去重...")
    df = remove_invalid_ids(df)
    after_id = len(df)
    print()

    # ---- Step 3: 内容去重 ----
    print("[STEP 3] Content 内容去重...")
    df = remove_duplicate_content(df)
    after_content = len(df)
    print()

    # ---- Step 4: 长度过滤 ----
    print("[STEP 4] 文本长度过滤...")
    df = filter_by_text_length(df)
    after_len = len(df)
    print()

    # ---- Step 5: 内容质量清洗 ----
    print("[STEP 5] 内容质量清洗（Emoji/标点/重复符号/引流词）...")
    df = filter_by_content_quality(df)
    final_count = len(df)
    print()

    # ---- Step 6: 统计输出 ----
    print("[STEP 6] 生成统计报告...")
    save_statistics(raw_count, after_id, after_content, after_len, final_count, STATS_FILE)

    # ---- Step 7: 结果导出 ----
    print("[STEP 7] 导出清洗后数据...")
    # 使用 utf-8-sig 编码（带 BOM 头），确保 Excel / 记事本直接打开中文不乱码
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"[INFO] 清洗后数据已保存至: {OUTPUT_FILE}")
    print(f"[INFO] 最终保留: {final_count:,} 条 / {raw_count:,} 条 "
          f"({final_count / raw_count * 100:.2f}%)")


# ==================== 程序入口 ====================
if __name__ == "__main__":
    main()
