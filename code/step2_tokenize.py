# -*- coding: utf-8 -*-
"""
=============================================================================
脚本名称: step2_tokenize.py
功能描述: 对清洗后的评论文本进行精细化分词与特征过滤，
         生成符合后续分析要求的空格分隔词序列。
=============================================================================

本脚本是数据处理流水线的第二步，在上一步清洗的基础上，对评论文本进行中文分词。

【处理流程】
  1. 加载专属领域词库 —— 歌曲名、网络流行语等专属名词，防止被 jieba 切碎
  2. 加载停用词表 —— 过滤高频无意义词（"的"、"了"、"是"等）
  3. 对每条评论执行 jieba 精确模式分词
  4. 过滤不符合要求的词：长度<2、停用词、纯数字、纯英文
  5. 输出空格分隔的分词结果

【核心技术点】
  - jieba.add_word() 动态注入领域词库，提升专属名词的分词准确率
  - 正则表达式预编译（re.compile）提高大数据量下的运行速度
  - 鲁棒的停用词加载机制：优先外部文件，失败时使用内置保底列表

【输入】comments_cleaned.csv（上一步清洗后的数据）
【输出】comments_tokenized.csv（新增 Words_Space_Separated 列，包含分词结果）
=============================================================================
"""

import os
import re
import pandas as pd
import jieba

# ---- 统一基于脚本所在目录定位所有文件 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# ======================================================================
# 第一部分：专属领域词库加载
# ======================================================================
# 背景：jieba 的默认词库是通用词库，对于歌曲评论中的专有名词
# （歌名、歌手名、网络流行语等）切分不准确。
# 例如："恋爱脑" 可能被切成 "恋爱" + "脑"，失去原意。
# 解决：通过 jieba.add_word() 将这些词预先加入词典，确保不被切碎。

FALLBACK_DOMAIN_WORDS = [
    # ---- 歌曲相关专属名词 ----
    "如果可以", "韦礼安", "九把刀", "月老", "红线",
    "单曲循环", "编曲", "原曲",
    # ---- 网络情感流行语 ----
    "恋爱脑", "回忆脑", "画大饼", "前夫哥", "意难平", "白月光",
    "纯爱战神", "曲中人", "深夜emo",
    # ---- 心理 / 情感专业词汇 ----
    "患得患失", "原生家庭", "精神内耗", "情绪价值", "边界感",
    "冷暴力", "讨好型", "社恐",
    # ---- 网络热词 ----
    "破防", "摆烂", "内耗", "海王", "救赎", "执念",
    "聊天框", "朋友圈", "释怀", "上头", "下头",
    # ---- 成语 / 常见搭配 ----
    "双向奔赴", "得偿所愿", "翻篇", "顺遂", "错付", "随缘",
    "散场", "同频", "共情", "甘拜下风", "自作多情", "背道而驰",
    "冷暖自知", "感同身受", "刻骨铭心", "触景生情",
    "撕心裂肺", "怦然心动", "喜极而泣", "强颜欢笑", "泪目",
    # ---- 平台相关 ----
    "网易云", "暖评", "高赞",
]


def load_domain_words(dict_path: str) -> list:
    """
    加载专属领域词库。

    策略：优先读取外部词典文件 jieba_user_dict.txt，
    若文件不存在则使用内置保底词库 FALLBACK_DOMAIN_WORDS。
    每行一个词，忽略空行及首尾空白字符。

    参数:
        dict_path: jieba_user_dict.txt 的完整路径

    返回:
        list: 领域词汇列表
    """
    if os.path.exists(dict_path):
        words = []
        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip()
                if w:  # 跳过空行
                    words.append(w)
        print(f"[提示] 成功加载领域词库: {dict_path}，共 {len(words)} 个词")
        return words
    else:
        print(f"[提示] 未检测到 {dict_path}，使用内置保底词库，共 {len(FALLBACK_DOMAIN_WORDS)} 个词")
        return list(FALLBACK_DOMAIN_WORDS)


# 加载领域词库并逐个注入 jieba 分词器
DOMAIN_DICT_PATH = os.path.join(SCRIPT_DIR, "..", "data", "jieba_user_dict.txt")
DOMAIN_WORDS = load_domain_words(DOMAIN_DICT_PATH)
for word in DOMAIN_WORDS:
    jieba.add_word(word)  # 将领域词汇加入 jieba 词典，使其在分词时被识别为完整词


# ======================================================================
# 第二部分：停用词加载（鲁棒性设计）
# ======================================================================
# 停用词是在文本分析中需要过滤掉的高频无意义词汇，
# 如 "的"、"了"、"在"、"是" 等，它们出现频率极高但对情感分析无贡献。

# 内置的高频中文停用词保底列表（约 70 个核心停用词）
DEFAULT_STOP_WORDS = {
    "的", "了", "在", "是", "我", "你", "他", "她", "它", "们",
    "都", "也", "就", "不", "吧", "啊", "呀", "呢", "吗", "哦",
    "这", "那", "有", "去", "到", "说", "要", "和", "与", "或",
    "而", "及", "等", "着", "一个", "没有", "很", "会", "能", "把",
    "被", "让", "给", "从", "对", "向", "用", "以",
    "我们", "你们", "他们", "自己", "之",
    "而且", "但是", "因为", "所以", "如果",
}

# 外部停用词文件路径（如存在，会与内置列表合并）
STOP_WORDS_PATH = os.path.join(SCRIPT_DIR, "src", "stop_words.txt")


def load_stop_words(file_path: str) -> set:
    """
    加载停用词表。

    策略：优先读取外部停用词文件并合并到内置列表；
    若文件不存在或读取失败，则仅使用内置保底停用词。

    参数:
        file_path: 外部停用词文件路径

    返回:
        set: 停用词集合（集合查找效率 O(1)，优于列表）
    """
    stop_words = set(DEFAULT_STOP_WORDS)  # 从内置保底列表开始

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip()
                    if word:
                        stop_words.add(word)  # 合并外部停用词
            print(f"[提示] 成功加载外部停用词表: {file_path}，停用词总数: {len(stop_words)}")
        except Exception as e:
            print(f"[警告] 加载外部停用词表失败: {e}。将使用内置保底停用词。")
    else:
        print(f"[提示] 未检测到外部停用词表 {file_path}，使用内置保底停用词，总数: {len(stop_words)}")

    return stop_words


# 一次性初始化停用词集合（全局变量，所有评论共用）
STOP_WORDS = load_stop_words(STOP_WORDS_PATH)


# ======================================================================
# 第三部分：分词与过滤规则
# ======================================================================
# 性能优化：正则表达式预编译（re.compile），避免每次调用都重新编译

RE_PURE_DIGIT = re.compile(r'^\d+$')          # 纯数字（如 "123"）
RE_PURE_ENGLISH = re.compile(r'^[a-zA-Z]+$')    # 纯英文字符（如 "hello"）


def tokenize_text(text: str) -> str:
    """
    对单条评论文本执行分词 → 清洗 → 过滤的完整流程。

    处理步骤:
      1. jieba.lcut() 精确模式分词 —— 将中文文本切分成词语列表
      2. 过滤长度小于 2 的词 —— 单字通常缺乏独立语义
      3. 过滤停用词 —— 高频无意义词
      4. 过滤纯数字 —— 数字本身不含情感信息
      5. 过滤纯英文 —— 除 "VIP" 外（网易云评论区常用标识）
      6. 用空格连接保留的词

    参数:
        text: 单条评论原始文本

    返回:
        str: 空格分隔的分词结果，如 "如果可以 那天 相遇 回忆"
             若输入为空或无效，返回空字符串 ""
    """
    # 防御性检查：确保输入是有效的字符串
    if not isinstance(text, str) or pd.isna(text):
        return ""

    # ===== 步骤 1: jieba 精确模式分词 =====
    # lcut() 返回列表（而非生成器），方便后续多次遍历
    # strip() 去除首尾空白，避免产生空 token
    tokens = jieba.lcut(text.strip())

    filtered_tokens = []
    for token in tokens:
        token = token.strip()

        # ===== 规则 1: 过滤长度小于 2 的词 =====
        # 单字词（如 "的"、"啊"）通常缺乏独立情感语义
        if len(token) < 2:
            continue

        # ===== 规则 2: 过滤停用词 =====
        # 使用集合查找，时间复杂度 O(1)
        if token in STOP_WORDS:
            continue

        # ===== 规则 3: 过滤纯数字 =====
        # 如 "2024"、"123"，不含分析价值
        if RE_PURE_DIGIT.match(token):
            continue

        # ===== 规则 4: 过滤纯英文，保留特定词 =====
        # 纯英文词在中文评论中通常无意义，但 "VIP" 是网易云的特有标识
        if RE_PURE_ENGLISH.match(token):
            if token.upper() != "VIP":
                continue

        # 通过所有过滤规则，保留该词
        filtered_tokens.append(token)

    # ===== 步骤 5: 空格分隔输出 =====
    # 格式："词1 词2 词3 ..."，方便后续 Counter 统计和 LDA 建模
    return " ".join(filtered_tokens)


# ======================================================================
# 第四部分：主执行流程
# ======================================================================

def main():
    """
    分词处理主流程。

    读取上一步清洗后的数据 → 逐条评论分词 → 保存结果
    """
    input_path = os.path.join(SCRIPT_DIR, "comments_cleaned.csv")
    output_path = os.path.join(SCRIPT_DIR, "comments_tokenized.csv")

    # 检查输入文件是否存在
    if not os.path.exists(input_path):
        print(f"[错误] 找不到输入文件 {input_path}，请确认上一步清洗是否成功。")
        return

    print("正在读取数据...")
    # 读取清洗后的数据，ID 字段强制为字符串类型
    df = pd.read_csv(input_path, dtype={
        "Comment_ID": str,
        "User_ID": str,
        "Replied_User_ID": str
    })

    print("正在进行精细分词与特征过滤...")
    # 处理空值：将 NaN 替换为空字符串
    df["Content"] = df["Content"].fillna("")

    # 核心步骤：对 Content 列的每条评论应用 tokenize_text 函数
    # 结果存入新增的 Words_Space_Separated 列
    df["Words_Space_Separated"] = df["Content"].apply(tokenize_text)

    print("正在保存分词结果...")
    # 保存结果，utf-8-sig 编码确保 Excel 直接打开不乱码
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[成功] 分词处理完成，结果已保存至: {output_path}")


if __name__ == "__main__":
    main()
