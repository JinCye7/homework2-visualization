# -*- coding: utf-8 -*-
"""
=============================================================================
脚本名称: step3_analyze_aggregate.py
功能描述: 读取分词后的评论文本，依次执行：
          多进程情感评分 → LDA 主题聚类 → 多维度静态图表绘制 → 前端 JSON 数据包导出
=============================================================================

本脚本是数据处理流水线的第三步（核心分析步骤），完成所有计算密集型任务。

【处理流程】
  1. 加载分词后的数据（comments_tokenized.csv）
  2. 日期标准化解析（Unix 时间戳 / 相对时间 → 标准日期格式）
  3. 混合情感分析打分（55% 中文情感词典 + 45% SnowNLP）
  4. 全局词频统计（Counter 计数）
  5. LDA 主题聚类建模（4 个主题）
  6. 生成 9 张静态可视化图表（PNG，保存至 images/ 目录）
  7. 代表性评论抽样（1200 条，分层抽样）
  8. 时序数据聚合（按年月分组统计）
  9. 导出前端 JSON 数据包（dashboard_data.json）

【核心优化】
  - 多进程并发（ProcessPoolExecutor）处理 74K+ 条评论，充分利用多核 CPU
  - 混合情感模型：自建中文情感词典 + SnowNLP，修正后者对音乐评论的偏差
  - Pandas → Python 原生类型转换，避免 numpy.int64 导致 JSON 序列化失败

【输入】comments_tokenized.csv（分词后的数据）
【输出】dashboard_data.json（前端数据）、images/*.png（图表）、comments_analyzed.csv（中间结果）
=============================================================================
"""

import os
import sys
import json
import warnings
from concurrent.futures import ProcessPoolExecutor  # 多进程执行器
from collections import Counter                      # 词频统计

import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import seaborn as sns

# ---- 导入自建的中文情感词典模块 ----
# sys.path.insert 确保脚本所在目录在 Python 搜索路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sentiment_lexicon import hybrid_sentiment_score as calc_hybrid_score
from sentiment_lexicon import classify_sentiment as lex_classify_sentiment

# 忽略 matplotlib/seaborn 的次要警告，保持终端整洁
warnings.filterwarnings("ignore")


# ======================================================================
# 第一部分：路径与全局配置
# ======================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "comments_tokenized.csv")       # 输入：分词数据
JSON_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "dashboard_data.json")    # 输出：前端 JSON
IMG_DIR = os.path.join(SCRIPT_DIR, "images")                          # 输出：图表目录

# 确保图片输出目录存在，不存在则自动创建
os.makedirs(IMG_DIR, exist_ok=True)


# ======================================================================
# 第二部分：系统字体与中文环境配置
# ======================================================================

def setup_visual_style():
    """
    配置 Matplotlib / Seaborn 的中文字体显示和绘图风格。

    关键步骤:
      1. 设置 font.sans-serif 字体回退列表（按优先级排列）
      2. 关闭 unicode_minus，防止负号显示为方块
      3. 应用 Seaborn whitegrid 主题

    为什么需要手动配置？
      Matplotlib 默认字体不支持中文，不配置会导致中文标题和标签显示为乱码方框。
    """
    # 中文字体优先级列表：按系统常见程度排列
    font_sans_serif = [
        'SimHei', 'Microsoft YaHei', 'PingFang SC',
        'Heiti SC', 'Arial Unicode MS', 'STHeiti', 'DejaVu Sans'
    ]

    # 安全拼接已有字体列表（防止某些环境返回非 list 对象）
    existing_fonts = list(plt.rcParams.get('font.sans-serif', []))
    plt.rcParams['font.sans-serif'] = font_sans_serif + existing_fonts
    # 解决负号 '-' 显示为方块的问题
    plt.rcParams['axes.unicode_minus'] = False

    # 应用 Seaborn 白色网格主题
    sns.set_theme(style="whitegrid",
                  rc={"font.sans-serif": font_sans_serif, "axes.unicode_minus": False})


def find_system_chinese_font_path() -> str | None:
    """
    搜寻系统中可用于 WordCloud 绘制的 .ttf / .ttc 物理字体文件路径。

    WordCloud 库需要直接指定字体文件路径（无法使用 Matplotlib 的字体回退机制），
    因此需要在系统中手动查找可用的中文字体文件。

    查找顺序:
      1. Windows 常见字体路径（C:\Windows\Fonts\）
      2. macOS 常见字体路径（/System/Library/Fonts/）
      3. Linux 常见字体路径（/usr/share/fonts/）
      4. 通过 matplotlib.font_manager 查找（兜底方案）

    返回:
        str | None: 找到的字体文件完整路径，找不到则返回 None
    """
    # 各系统常见中文字体路径列表
    candidates = [
        "C:\\Windows\\Fonts\\msyh.ttc",                           # Windows 微软雅黑
        "C:\\Windows\\Fonts\\msyh.ttf",
        "C:\\Windows\\Fonts\\simhei.ttf",                         # Windows 黑体
        "/System/Library/Fonts/PingFang.ttc",                     # macOS 苹方
        "/System/Library/Fonts/STHeiti Light.ttc",                # macOS 华文黑体
        "/Library/Fonts/Arial Unicode.ttf",                       # macOS Arial Unicode
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",        # Linux 文泉驿微米黑
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",          # Linux 文泉驿正黑
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", # Linux Noto Sans CJK
    ]

    # 逐一检查候选路径是否存在
    for path in candidates:
        if os.path.exists(path):
            return path

    # 兜底：通过 matplotlib 的字体管理器搜索
    try:
        import matplotlib.font_manager as fm
        for f in fm.findSystemFonts():
            f_lower = f.lower()
            if any(name in f_lower for name in ['simhei', 'yahei', 'pingfang', 'wqy', 'heiti']):
                return f
    except Exception:
        pass  # 静默失败

    return None  # 未找到可用中文字体


# 在模块加载时完成配置
setup_visual_style()
CHINESE_FONT_PATH = find_system_chinese_font_path()


# ======================================================================
# 第三部分：鲁棒日期解析模块
# ======================================================================

def parse_dates_robustly(df: pd.DataFrame) -> pd.DataFrame:
    """
    鲁棒地解析评论日期，处理多种日期格式。

    网易云 API 返回的评论时间有两种格式:
      1. Timestamp 字段 —— Unix 时间戳（毫秒或秒级）
      2. Time_String 字段 —— 可读格式（如 "2024年8月15日"）或相对时间（"3分钟前"）

    解析策略:
      1. 优先使用 Timestamp（精确），自动判断毫秒 / 秒级别
      2. 若 Timestamp 缺失，尝试以 mixed 模式解析 Time_String
      3. 生成统一的 Year_Month 格式（YYYY-MM），用于后续时序聚合

    参数:
        df: 包含时间相关字段的 DataFrame

    返回:
        pd.DataFrame: 新增 Datetime 和 Year_Month 列的 DataFrame
    """
    print("[提示] 正在进行日期标准化转换...")

    # ---- 方式 1: 解析 Unix 时间戳 ----
    if "Timestamp" in df.columns:
        ts_numeric = pd.to_numeric(df["Timestamp"], errors="coerce")
        max_ts = ts_numeric.max()
        # 自动判断时间戳单位：最大值 > 1e11 则为毫秒，否则为秒
        # （2024年的秒级时间戳约 1.7e9，毫秒级约 1.7e12）
        unit = "ms" if (not pd.isna(max_ts) and max_ts > 1e11) else "s"
        df["Datetime"] = pd.to_datetime(ts_numeric, unit=unit, errors="coerce")

    # ---- 方式 2: 解析文本时间字符串（兜底方案）----
    if "Datetime" not in df.columns or df["Datetime"].isna().all():
        # format="mixed" 使 pandas 尝试多种格式自动匹配
        df["Datetime"] = pd.to_datetime(df["Time_String"], errors="coerce", format="mixed")

    # ---- 提取年月标识 ----
    df["Year_Month"] = df["Datetime"].dt.strftime("%Y-%m")

    # ---- 极端情况：所有日期都无法解析 ----
    if df["Year_Month"].isna().all():
        print("[警告] 所有评论日期均无法解析，已采用当前日期进行兜底。")
        df["Year_Month"] = pd.Timestamp.now().strftime("%Y-%m")

    return df


# ======================================================================
# 第四部分：多进程情感分析打分引擎（核心改进模块）
# ======================================================================

def analyze_single_sentiment(text: str) -> float:
    """
    子进程执行函数：对单条文本进行混合情感打分。

    混合策略：
      - 55% 自建中文情感词典（lexicon_sentiment_score）
        —— 更适合中文音乐评论的感性语言
      - 45% SnowNLP（贝叶斯模型）
        —— 提供统计层面的参考信号

    相比纯 SnowNLP 的改进：
      SnowNLP 基于电商评论训练，对"回忆脑比恋爱脑更可怕"这类
      感性表达评分失真（误判为积极），词典可以修正这类偏差。

    参数:
        text: 单条评论文本

    返回:
        float: 情感分值（0=极端消极, 0.5=中性, 1=极端积极）
    """
    # 空文本返回中性值
    if not isinstance(text, str) or not text.strip():
        return 0.5

    try:
        from snownlp import SnowNLP
        # 计算 SnowNLP 原始得分
        snownlp_score = float(SnowNLP(text).sentiments)
        # 混合加权：55% 词典 + 45% SnowNLP
        return calc_hybrid_score(text, snownlp_score)
    except Exception:
        # SnowNLP 失败时的兜底：使用纯词典打分
        return calc_hybrid_score(text, None)


def run_parallel_sentiment(texts: list) -> list:
    """
    使用多进程并发处理情感分析，充分利用多核 CPU。

    原理:
      - ProcessPoolExecutor 创建进程池，每个子进程独立导入模块
      - chunksize = len(texts) // 16：将数据分成 16 个块，减少进程间通信开销
      - 74,384 条评论在 8 核 CPU 上约需 2~3 分钟

    参数:
        texts: 评论文本列表

    返回:
        list[float]: 与输入顺序对应的情感分值列表
    """
    print(f"[提示] 启动多进程情感打分引擎（混合模式：词典+Snownlp），处理数据行数: {len(texts)}...")

    # 预检查 SnowNLP 依赖
    try:
        import snownlp  # noqa: F401（仅标记导入，不做实际使用）
    except ImportError:
        print("[警告] 未检测到 snownlp 库。将使用纯词典打分。")

    scores = []
    # 创建进程池，默认使用所有可用 CPU 核心
    with ProcessPoolExecutor() as executor:
        # 每块约 4,649 条（74384/16），平衡并行度和通信成本
        chunksize = max(1, len(texts) // 16)
        scores = list(executor.map(analyze_single_sentiment, texts, chunksize=chunksize))

    print("[提示] 多进程情感打分处理完成。")
    return scores


def classify_sentiment(score: float) -> str:
    """
    根据情感分值进行三分类。

    阈值设计：
      - > 0.55 → 积极：明确的正向情感
      - 0.45 ~ 0.55 → 中性：无明显情感倾向
      - < 0.45 → 消极：明确的负向情感

    相比原始 SnowNLP（>0.6 / 0.4~0.6 / <0.4）的改进：
      词典混合评分后分布更均衡，不需要过宽的"中性"区间来吸收偏差。
      窄化的阈值能更准确地分类边缘情感。

    参数:
        score: 情感分值（0~1）

    返回:
        str: "积极" / "中性" / "消极"
    """
    return lex_classify_sentiment(score)


# ======================================================================
# 第五部分：静态图表生成模块
# ======================================================================

def generate_and_save_wordcloud(text: str, output_path: str, font_path: str = None):
    """
    根据输入的词频序列生成并保存词云图。

    技术细节:
      - 使用 wordcloud 库的 generate() 方法（非 generate_from_frequencies）
      - 输入为空格分隔的词序列，wordcloud 自动统计词频
      - 通过 font_path 指定中文字体，否则中文无法渲染

    参数:
        text:        空格分隔的词语序列（如 "喜欢 幸福 回忆 ..."）
        output_path: 输出 PNG 文件路径
        font_path:   中文字体 .ttf/.ttc 文件的完整路径
    """
    # 防御：空文本用占位词
    if not text.strip():
        text = "暂无 数据 空白 数据 序列"

    try:
        from wordcloud import WordCloud

        # 创建词云对象并生成图像
        wc = WordCloud(
            font_path=font_path,          # 中文字体路径（关键配置）
            background_color="white",     # 白色背景
            width=800,                    # 输出宽度（像素）
            height=400,                   # 输出高度（像素）
            max_words=100,                # 最多显示 100 个词
            random_state=42               # 固定随机种子，保证可复现
        ).generate(text)

        # 渲染并保存
        plt.figure(figsize=(10, 5))
        plt.imshow(wc, interpolation="bilinear")  # 双线性插值，平滑显示
        plt.axis("off")                           # 不显示坐标轴
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()

    except ImportError:
        print("[警告] 未安装 wordcloud 库，跳过生成该词云。")
    except Exception as e:
        print(f"[错误] 词云图生成失败 ({output_path}): {e}")


def plot_charts(df: pd.DataFrame, topics_data: list, top_words: list):
    """
    一键绘制并保存所需的 9 张统计与分析图表。

    图表清单:
      1. comment_length_distribution.png —— 评论长度分布直方图 + KDE
      2. likes_distribution.png          —— 点赞数对数分布直方图
      3. wordcloud_all.png               —— 全量评论词云
      4. top30_words.png                 —— Top 30 高频词水平条形图
      5. wordcloud_highlikes.png         —— 高赞评论词云
      6. wordcloud_normal.png            —— 普通评论词云
      7. sentiment_pie.png               —— 情感三分类饼图
      8. sentiment_timeline.png          —— 评论量与情感走势双轴时序图
      9. advanced_analysis.png           —— LDA 主题特征词权重图

    参数:
        df:          包含分词和情感分析结果的完整 DataFrame
        topics_data: LDA 主题聚类结果列表
        top_words:   Top 50 高频词列表 [(word, count), ...]
    """
    print("[提示] 正在绘制统计图表并将静态图输出至 ./images/ 目录...")

    # ===== 图表 1: 评论长度分布直方图 + KDE 曲线 =====
    plt.figure(figsize=(8, 5))
    # 确定长度列的列名
    length_col = "Text_Length" if "Text_Length" in df.columns else "Content_Len"
    if length_col not in df.columns:
        df[length_col] = df["Content"].fillna("").apply(len)  # 动态计算

    # KDE 曲线叠加在直方图上，展示分布的平滑趋势
    sns.histplot(df[length_col], kde=True, bins=30, color="#4c72b0")
    plt.title("评论长度分布图 (Comment Length Distribution)")
    plt.xlabel("评论字数")
    plt.ylabel("频数")
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "comment_length_distribution.png"), dpi=150)
    plt.close()

    # ===== 图表 2: 点赞数对数分布图 =====
    # 使用 log1p 变换：log(x+1)，避免 x=0 时 log(0) 为负无穷
    plt.figure(figsize=(8, 5))
    likes_log = np.log1p(df["Liked_Count"].fillna(0))  # log1p = ln(x+1)
    sns.histplot(likes_log, kde=True, bins=30, color="#dd8452")
    plt.title("点赞数对数分布图 (Likes Distribution with Log1p)")
    plt.xlabel("Log(点赞数 + 1)")
    plt.ylabel("频数")
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "likes_distribution.png"), dpi=150)
    plt.close()

    # ===== 图表 3: 全量评论词云 =====
    all_text = " ".join(df["Words_Space_Separated"].fillna("").astype(str))
    generate_and_save_wordcloud(all_text, os.path.join(IMG_DIR, "wordcloud_all.png"), CHINESE_FONT_PATH)

    # ===== 图表 4: Top 30 高频词水平条形图 =====
    if top_words:
        words, counts = zip(*top_words[:30])  # 解包取前 30 个
        plt.figure(figsize=(10, 8))
        # hue=words 用于创建渐变色（新版 Seaborn 要求），legend=False 隐藏图例
        sns.barplot(x=list(counts), y=list(words), hue=list(words),
                    palette="viridis", legend=False)
        plt.title("Top 30 评论高频词水平条形图")
        plt.xlabel("出现频数")
        plt.ylabel("词语")
        plt.tight_layout()
        plt.savefig(os.path.join(IMG_DIR, "top30_words.png"), dpi=150)
        plt.close()

    # ===== 图表 5 & 6: 高赞 vs 普通评论词云对比 =====
    median_likes = df["Liked_Count"].median()  # 点赞中位数作为分割线
    # 高赞评论（点赞数 >= 中位数）
    high_likes_mask = df["Liked_Count"] >= median_likes
    high_likes_text = " ".join(df[high_likes_mask]["Words_Space_Separated"].fillna("").astype(str))
    # 普通评论（点赞数 < 中位数）
    normal_likes_text = " ".join(df[~high_likes_mask]["Words_Space_Separated"].fillna("").astype(str))

    generate_and_save_wordcloud(high_likes_text, os.path.join(IMG_DIR, "wordcloud_highlikes.png"), CHINESE_FONT_PATH)
    generate_and_save_wordcloud(normal_likes_text, os.path.join(IMG_DIR, "wordcloud_normal.png"), CHINESE_FONT_PATH)

    # ===== 图表 7: 情感三分类饼图 =====
    plt.figure(figsize=(6, 6))
    sentiment_counts = df["Sentiment_Class"].value_counts()
    labels = sentiment_counts.index.tolist()
    sizes = sentiment_counts.values.tolist()

    # 绿=积极，黄=中性，红=消极
    color_map = {"积极": "#99ff99", "中性": "#fdfd96", "消极": "#ff9999"}
    colors = [color_map.get(l, "#aec6cf") for l in labels]

    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140, colors=colors,
            wedgeprops={'edgecolor': 'black', 'linewidth': 0.8, 'antialiased': True})
    plt.title("评论情感倾向分布比例")
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "sentiment_pie.png"), dpi=150)
    plt.close()

    # ===== 图表 8: 评论量与情感走势双轴时序图 =====
    timeline_df = df.dropna(subset=["Year_Month"])
    timeline = timeline_df.groupby("Year_Month").agg(
        comment_count=("Comment_ID", "count"),       # 每月评论数量
        avg_sentiment=("Sentiment_Score", "mean")    # 每月平均情感值
    ).reset_index().sort_values("Year_Month")

    if not timeline.empty:
        fig, ax1 = plt.subplots(figsize=(12, 6))

        # 左 Y 轴：评论量（柱状图）
        color_vol = "#4c72b0"
        ax1.set_xlabel("年月 (Year-Month)")
        ax1.set_ylabel("评论量", color=color_vol)
        ax1.bar(timeline["Year_Month"], timeline["comment_count"],
                color=color_vol, alpha=0.6, label="评论量")
        ax1.tick_params(axis='y', labelcolor=color_vol)
        plt.xticks(rotation=45)

        # 右 Y 轴：平均情感（折线图）
        ax2 = ax1.twinx()  # 创建共享 X 轴的双 Y 轴
        color_sent = "#c44e52"
        ax2.set_ylabel("平均情感得分", color=color_sent)
        ax2.plot(timeline["Year_Month"], timeline["avg_sentiment"],
                 color=color_sent, marker="o", linewidth=2.5, label="平均情感")
        ax2.tick_params(axis='y', labelcolor=color_sent)
        ax2.set_ylim(0, 1.0)  # 情感值范围固定在 [0, 1]

        plt.title("按年月统计评论量与情感走势双轴图")
        fig.tight_layout()
        plt.savefig(os.path.join(IMG_DIR, "sentiment_timeline.png"), dpi=150)
        plt.close()

    # ===== 图表 9: 情感分与点赞数的对数气泡散点图 =====
    plt.figure(figsize=(10, 6))
    x = df["Sentiment_Score"]                      # X 轴：情感分值
    y = np.log1p(df["Liked_Count"].fillna(0))      # Y 轴：对数点赞数
    # 气泡大小：基于回复数（若没有则用点赞数），越大越活跃
    reply_count_col = "Reply_Count" if "Reply_Count" in df.columns else "Liked_Count"
    sizes = np.log1p(df[reply_count_col].fillna(0)) * 50 + 20

    # 颜色映射：颜色越暖表示情感越积极
    scatter = plt.scatter(x, y, s=sizes, c=x, cmap="coolwarm",
                          alpha=0.6, edgecolors="grey", linewidth=0.5)
    plt.colorbar(scatter, label="情感得分")
    plt.title("评论情感评分与点赞对数关系气泡图")
    plt.xlabel("情感分 (Sentiment Score)")
    plt.ylabel("对数点赞数 Log(Liked Count + 1)")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(IMG_DIR, "sentiment_vs_likes.png"), dpi=150)
    plt.close()

    # ===== 图表 10: LDA 主题特征词权重图（4 个子图） =====
    if topics_data:
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        axes = axes.flatten()  # 将 2x2 展平为 1x4 数组
        for idx in range(4):
            ax = axes[idx]
            if idx < len(topics_data):
                topic = topics_data[idx]
                words = topic["words"]
                weights = topic["weights"]
                # 水平条形图（由高到低排列）
                ax.barh(words[::-1], weights[::-1],
                        color=sns.color_palette("muted")[idx])
                ax.set_title(f"主题 {topic['topic_id']} 特征词权重")
                ax.set_xlabel("权重")
                ax.grid(True, axis='x', linestyle="--", alpha=0.5)
            else:
                # 实际主题不足 4 个时，删除多余子图防止空白
                fig.delaxes(ax)

        plt.suptitle("LDA 主题聚类前 10 特征词分布与权重图", fontsize=16)
        plt.tight_layout()
        plt.savefig(os.path.join(IMG_DIR, "advanced_analysis.png"), dpi=150)
        plt.close()

    print("[成功] 所有图表均已成功生成，存放在: ./images/")


# ======================================================================
# 第六部分：代表性数据抽样逻辑
# ======================================================================

def select_representative_samples(df: pd.DataFrame, target_size: int = 1200) -> pd.DataFrame:
    """
    采取多维度分层抽样，确保采样点全面覆盖。

    抽样策略（三等分）:
      1. 高点赞评论（top 400）：评论中的"明星"，影响力最大
      2. 极端积极评论（top 400）：情感最正面的代表
      3. 极端消极评论（bottom 400）：情感最负面的代表
      4. 若不足 1200 条，用随机采样补齐

    这样保证前端散点图中每个象限都有充足的代表性样本。

    参数:
        df:          完整数据
        target_size: 目标采样数量（默认 1200）

    返回:
        pd.DataFrame: 采样后的代表性子集
    """
    if len(df) <= target_size:
        return df  # 数据不足时全量返回

    quota = target_size // 3  # 每层配额：1200/3 = 400

    # 第一层：高点赞评论（按点赞数降序取前 400）
    high_likes = df.nlargest(quota, "Liked_Count")

    # 第二层：极端积极（按情感分降序取前 400，排除已选的）
    remaining_df = df[~df["Comment_ID"].isin(high_likes["Comment_ID"])]
    extreme_pos = remaining_df.nlargest(quota, "Sentiment_Score")

    # 第三层：极端消极（按情感分升序取前 400，即最低分）
    remaining_df = remaining_df[~remaining_df["Comment_ID"].isin(extreme_pos["Comment_ID"])]
    extreme_neg = remaining_df.nsmallest(quota, "Sentiment_Score")

    # 合并三层样本
    samples = pd.concat([high_likes, extreme_pos, extreme_neg])

    # 第四步：随机补齐不足部分
    remaining_df = df[~df["Comment_ID"].isin(samples["Comment_ID"])]
    needed = target_size - len(samples)
    if needed > 0 and len(remaining_df) > 0:
        random_samples = remaining_df.sample(min(needed, len(remaining_df)), random_state=42)
        samples = pd.concat([samples, random_samples])

    return samples


# ======================================================================
# 第七部分：LDA 主题提取模块
# ======================================================================

def run_lda_modeling(df: pd.DataFrame, num_topics: int = 4) -> list:
    """
    使用 scikit-learn 的 LatentDirichletAllocation 建立主题模型。

    LDA（潜在狄利克雷分配）是无监督主题建模算法，可以自动从大量文档中
    发现潜在的主题结构。每条评论被视为多个主题的混合，每个主题由一组
    高权重特征词定义。

    流程:
      1. CountVectorizer 构建词频矩阵（词袋模型）
      2. LDA 拟合，发现 4 个隐含主题
      3. 提取每个主题的 Top 10 特征词及其权重

    参数:
        df:         包含 Words_Space_Separated 列的 DataFrame
        num_topics: 期望发现的主题数（默认 4）

    返回:
        list[dict]: 每个主题的 {topic_id, words, weights}
    """
    print("[提示] 正在构建 LDA 主题聚类模型...")

    # 准备文档列表（每条评论为一个文档）
    documents = df["Words_Space_Separated"].fillna("").astype(str).tolist()
    valid_documents = [doc for doc in documents if doc.strip()]

    if not valid_documents:
        print("[警告] 无有效分词序列，LDA 主题模型跳过。")
        return []

    try:
        from sklearn.feature_extraction.text import CountVectorizer
        from sklearn.decomposition import LatentDirichletAllocation

        # ---- 步骤 1: 构建词频矩阵 ----
        # max_features=1000: 只保留最常见的 1000 个词，过滤噪声
        # max_df=0.9: 在 90% 以上文档中出现的词视为常见词，过滤
        # min_df=2: 至少在 2 个文档中出现才保留
        vectorizer = CountVectorizer(max_features=1000, max_df=0.9, min_df=2)
        tf = vectorizer.fit_transform(valid_documents)

        if tf.shape[1] == 0:
            print("[警告] 特征矩阵为空，无法进行LDA分析。")
            return []

        # ---- 步骤 2: LDA 拟合 ----
        # random_state=42: 固定随机种子保证可复现
        # max_iter=10: 最大迭代次数（数据集大时使用较小的值）
        lda = LatentDirichletAllocation(n_components=num_topics, random_state=42, max_iter=10)
        lda.fit(tf)

        # ---- 步骤 3: 提取主题特征词 ----
        feature_names = vectorizer.get_feature_names_out()
        topics_data = []

        for topic_idx, topic in enumerate(lda.components_):
            # 获取权重最高的前 10 个词的索引
            top_features_ind = topic.argsort()[:-11:-1]  # 倒序取前 10
            top_words = [feature_names[i] for i in top_features_ind]
            top_weights = [float(topic[i]) for i in top_features_ind]

            topics_data.append({
                "topic_id": topic_idx + 1,
                "words": top_words,
                "weights": top_weights
            })

        print(f"[提示] LDA 模型拟合成功，共提取 {num_topics} 个主题类别。")
        return topics_data

    except Exception as e:
        print(f"[错误] LDA 主题建模运行失败: {e}")
        return []


# ======================================================================
# 第八部分：主控工作流
# ======================================================================

def main():
    """
    主控工作流：按顺序执行所有分析步骤。

    Step 1: 加载分词数据 + 数据类型修复
    Step 2: 日期标准化解析
    Step 3: 混合情感打分（多进程）
    Step 4: 全局词频统计
    Step 5: LDA 主题聚类
    Step 6: 生成静态可视化图表
    Step 7: 代表性评论抽样
    Step 8: 时序数据聚合
    Step 9: 构建并导出前端 JSON 数据包
    """
    # ---- 前置检查 ----
    if not os.path.exists(INPUT_PATH):
        print(f"[错误] 未检测到分词输入源文件: {INPUT_PATH}。请检查前面的分词步骤。")
        return

    print("正在加载分词评论数据...")
    df = pd.read_csv(INPUT_PATH, dtype={
        "Comment_ID": str,
        "User_ID": str,
        "Replied_User_ID": str
    })

    # ---- 数据类型修复 ----
    # 对数值列进行强制类型转换 + 空值填充，彻底消除脏数据隐患
    df["Liked_Count"] = pd.to_numeric(df["Liked_Count"], errors="coerce").fillna(0).astype(int)
    if "Reply_Count" in df.columns:
        df["Reply_Count"] = pd.to_numeric(df["Reply_Count"], errors="coerce").fillna(0).astype(int)
    if "Text_Length" in df.columns:
        df["Text_Length"] = pd.to_numeric(df["Text_Length"], errors="coerce").fillna(0).astype(int)

    # ---- 日期解析 ----
    df = parse_dates_robustly(df)

    # ---- Step 1: 混合情感打分（多进程）----
    df["Content"] = df["Content"].fillna("").astype(str)
    df["Sentiment_Score"] = run_parallel_sentiment(df["Content"].tolist())
    df["Sentiment_Class"] = df["Sentiment_Score"].apply(classify_sentiment)

    # 保存中间结果
    processed_csv_path = os.path.join(SCRIPT_DIR, "comments_analyzed.csv")
    df.to_csv(processed_csv_path, index=False, encoding="utf-8-sig")
    print(f"[提示] 情感分析结果已回写并保存至: {processed_csv_path}")

    # ---- Step 2: 全局词频统计 ----
    all_words = []
    for s in df["Words_Space_Separated"].fillna("").astype(str):
        words = s.split()
        # 只统计长度 >= 2 的词（与分词过滤逻辑保持一致）
        all_words.extend([w for w in words if len(w) >= 2])

    word_counts = Counter(all_words)
    top_words_list = word_counts.most_common(50)  # Top 50 高频词

    # ---- Step 3: LDA 主题聚类 ----
    topics_data = run_lda_modeling(df, num_topics=4)

    # ---- Step 4: 生成图表 ----
    plot_charts(df, topics_data, top_words_list)

    # ---- Step 5: 代表性评论抽样 ----
    samples_df = select_representative_samples(df, target_size=1200)

    # 确保目标列都存在
    target_columns = ["Comment_ID", "Nickname", "Content", "Liked_Count",
                      "Sentiment_Score", "Sentiment_Class", "Time_String"]
    for col in target_columns:
        if col not in samples_df.columns:
            samples_df[col] = "N/A"

    # ---- 类型转换：Pandas → Python 原生类型 ----
    # 关键步骤：将 numpy.int64 / float64 转为 Python 原生 int / float，
    # 否则 json.dump() 会抛出 TypeError
    raw_sampled_list = samples_df[target_columns].to_dict(orient="records")
    sampled_comments_list = []
    for record in raw_sampled_list:
        cleaned_record = {}
        for k, v in record.items():
            if isinstance(v, (np.integer, np.int64, np.int32)):
                cleaned_record[k] = int(v)
            elif isinstance(v, (np.floating, np.float64, np.float32)):
                cleaned_record[k] = float(v)
            elif pd.isna(v):
                cleaned_record[k] = None
            else:
                cleaned_record[k] = v
        sampled_comments_list.append(cleaned_record)

    # ---- Step 6: 时序数据聚合 ----
    timeline_df = df.dropna(subset=["Year_Month"])
    timeline_grouped = timeline_df.groupby("Year_Month").agg(
        comment_count=("Comment_ID", "count"),
        avg_sentiment=("Sentiment_Score", "mean")
    ).reset_index().sort_values("Year_Month")

    timeline_list = []
    for _, row in timeline_grouped.iterrows():
        timeline_list.append({
            "year_month": str(row["Year_Month"]),
            "comment_count": int(row["comment_count"]),
            "avg_sentiment": float(row["avg_sentiment"])
        })

    # ---- Step 7: 构建前端 JSON 数据包 ----
    dashboard_data = {
        "summary_statistics": {
            "total_comments": int(len(df)),
            "average_sentiment": float(df["Sentiment_Score"].mean()) if len(df) > 0 else 0.5,
            "positive_count": int((df["Sentiment_Class"] == "积极").sum()),
            "neutral_count": int((df["Sentiment_Class"] == "中性").sum()),
            "negative_count": int((df["Sentiment_Class"] == "消极").sum()),
            "max_likes": int(df["Liked_Count"].max()) if len(df) > 0 else 0,
            "average_length": float(df["Text_Length"].mean()) if "Text_Length" in df.columns
                              else float(df["Content"].apply(len).mean())
        },
        "timeline_data": timeline_list,
        "top_words": [{"word": w, "count": c} for w, c in top_words_list],
        "lda_topics": topics_data,
        "sampled_comments": sampled_comments_list
    }

    # ---- 导出 JSON ----
    with open(JSON_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=4)
    print(f"[成功] 前端可视化大屏数据已打包输出至: {JSON_OUTPUT_PATH}")


# ==================== 程序入口 ====================
if __name__ == "__main__":
    main()
