# -*- coding: utf-8 -*-
"""
=============================================================================
脚本名称: enrich_data.py
功能描述: 对已分析的数据进行深度叙事驱动分析，
         生成 enriched_data.json 供交互式可视化页面使用。
=============================================================================

本脚本在 step3_analyze_aggregate.py 之后运行，对已完成情感打分的评论数据
进行多维度深度分析。所有分析结果以 JSON 格式输出，供前端 ECharts 图表消费。

【分析维度】
  1. 情感关键词类别    —— 六大情感主题的评论覆盖量
  2. 地理分布           —— 评论者 IP 归属地 Top 25
  3. 时段发布模式       —— 24 小时评论分布 + 深夜活跃率
  4. 评论长度分段       —— 按字数分段的评论量、情感均值、点赞均值
  5. 月度互动趋势       —— 每月评论量、情感、点赞的聚合统计
  6. 峰值时刻           —— 评论量最高月 + 情感值最高月
  7. 精选评论           —— 分维度精选代表性评论（最高赞/最积极/最感性/长篇故事）
  8. 情感变化速度       —— 月度情感值的环比变化量
  9. 词语共现网络       —— 8 个核心情感词的 Jaccard / NPMI / Phi 共现系数
  10. 年度对比          —— 按年聚合的评论量与情感对比
  11. 叙事统计摘要      —— 总评论数、用户数、情感占比等汇总指标

【输入】comments_analyzed.csv（已完成情感打分的完整数据）
【输出】enriched_data.json（前端可视化数据）
=============================================================================
"""

import json
import os
import re
import numpy as np
import pandas as pd
from collections import defaultdict

# ---- 基于脚本所在目录定位所有文件 ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_CSV = os.path.join(SCRIPT_DIR, "comments_analyzed.csv")        # 输入：已分析数据
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "enriched_data.json")        # 输出：深度分析 JSON


# ======================================================================
# 辅助工具函数：安全类型转换
# ======================================================================

def safe_int(v):
    """安全转换为 int，失败返回 0"""
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0


def safe_float(v):
    """安全转换为 float，失败返回 0.0"""
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def clean_records(records):
    """
    将 numpy 数据类型转换为 Python 原生类型，确保 JSON 序列化安全。

    背景：pandas DataFrame 的 to_dict() 返回的值可能是 numpy.int64 / float64，
    而 Python 标准库的 json.dump() 无法序列化这些类型，会抛出 TypeError。
    此函数递归将每个字段显式转换为 Python 原生 int / float / str / None。

    参数:
        records: DataFrame.to_dict(orient="records") 的结果列表

    返回:
        list[dict]: 所有值均为 Python 原生类型的记录列表
    """
    cleaned = []
    for r in records:
        item = {}
        for k, v in r.items():
            if isinstance(v, (np.integer,)):
                item[k] = int(v)
            elif isinstance(v, (np.floating,)):
                item[k] = float(v)
            elif pd.isna(v):
                item[k] = None
            else:
                # 对于非数值、非空值，统一转为字符串（保留原始表达能力）
                item[k] = str(v) if not isinstance(v, (int, float, list, dict, type(None))) else v
        cleaned.append(item)
    return cleaned


# ======================================================================
# 主分析流程
# ======================================================================

def main():
    """
    执行全部 11 个维度的深度分析，并输出 enriched_data.json。
    """
    print("Loading analyzed data...")
    # 加载已分析数据，强制 ID 为字符串类型
    df = pd.read_csv(INPUT_CSV, dtype={"Comment_ID": str}, low_memory=False)
    # 数据类型修复：确保数值列为正确的 Python 类型
    df["Liked_Count"] = pd.to_numeric(df["Liked_Count"], errors="coerce").fillna(0).astype(int)
    df["Sentiment_Score"] = pd.to_numeric(df["Sentiment_Score"], errors="coerce").fillna(0.5)
    df["Content"] = df["Content"].fillna("").astype(str)

    enriched = {}  # 最终输出的 JSON 字典

    # ==================================================================
    # 维度 1：情感关键词类别分析
    # ==================================================================
    # 六大情感主题各对应一组关键词，统计包含至少一个关键词的评论数。
    # 每条评论对每个类别最多贡献 1 次（正则 OR 匹配），避免重复计数。
    print("Analyzing emotional keywords...")
    emotion_dict = {
        "思念与遗憾": ["回忆", "想念", "遗憾", "回到", "过去", "后悔", "错过", "失去", "如果", "忘不了", "放不下", "舍不得"],
        "爱情与承诺": ["喜欢", "爱你", "在一起", "结婚", "永远", "守护", "陪伴", "约定", "承诺", "等待", "珍惜", "表白", "求婚"],
        "眼泪与感动": ["哭了", "流泪", "泪目", "感动", "好听", "治愈", "破防", "绷不住", "听哭", "哭泣", "泪奔", "心碎"],
        "希望与祝福": ["加油", "幸福", "希望", "祝福", "好运", "健康", "快乐", "开心", "顺利", "平安", "美好", "未来"],
        "青春与时光": ["青春", "时光", "岁月", "小时候", "学生", "那年", "曾经", "年轻", "长大", "成长", "少年", "校园"],
        "孤独与自语": ["一个人", "孤独", "难过", "伤心", "失眠", "夜晚", "凌晨", "深夜", "偷偷", "沉默", "安静", "独白"]
    }

    # 使用正则 OR 模式匹配：每条评论对每个类别只计 1 次
    # 例如 "思念与遗憾" 的 pattern = "回忆|想念|遗憾|...|舍不得"
    emotion_counts = {}
    for category, keywords in emotion_dict.items():
        # re.escape() 确保包含特殊字符的关键词被正确转义
        pattern = '|'.join(re.escape(kw) for kw in keywords)
        # str.contains() 返回布尔 Series，sum() 计数
        count = df["Content"].str.contains(pattern, na=False, regex=True).sum()
        emotion_counts[category] = int(count)

    # 按数量降序排列，前端展示更直观
    enriched["emotion_categories"] = [
        {"category": k, "count": v} for k, v in
        sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # ==================================================================
    # 维度 2：地理分布分析
    # ==================================================================
    # 基于评论者的 IP_Location 字段，统计各省份的评论数量
    print("Analyzing geographic distribution...")
    if "IP_Location" in df.columns:
        geo = df["IP_Location"].fillna("未知").value_counts().head(25)
        enriched["geo_distribution"] = [
            {"name": str(k), "value": int(v)} for k, v in geo.items() if k and k != "未知"
        ]
    else:
        enriched["geo_distribution"] = []  # 无地理位置数据时输出空列表

    # ==================================================================
    # 维度 3：时段发布模式
    # ==================================================================
    # 从 Datetime 字段提取小时，统计 24 小时评论分布
    # 同时计算"深夜活跃率"：22:00 ~ 次日 06:00 的评论占比
    print("Analyzing hourly patterns...")
    if "Datetime" in df.columns:
        # 提取小时（0~23）
        df["Hour"] = pd.to_datetime(df["Datetime"], errors="coerce").dt.hour
        hourly = df["Hour"].dropna().value_counts().sort_index()
        enriched["hourly_pattern"] = [
            {"hour": int(h), "count": int(c)} for h, c in hourly.items()
        ]
        # 深夜区间：22点~23点 或 0点~6点
        night_mask = (df["Hour"] >= 22) | (df["Hour"] <= 6)
        enriched["night_owl_ratio"] = round(float(night_mask.sum() / len(df) * 100), 1)
    else:
        enriched["hourly_pattern"] = []
        enriched["night_owl_ratio"] = 0

    # ==================================================================
    # 维度 4：评论长度分段分析
    # ==================================================================
    # 将评论按字数分为 5 段，统计每段的评论量、平均情感、平均点赞
    print("Analyzing comment length segments...")
    # pd.cut() 将连续值离散化到指定的区间
    df["len_seg"] = pd.cut(
        df["Content"].apply(len),   # 计算每条评论的实际字符数
        bins=[0, 10, 20, 40, 80, 500],  # 分段边界
        labels=["短评 (≤10字)", "简评 (11-20字)", "中评 (21-40字)", "长评 (41-80字)", "超长评 (>80字)"]
    )
    # observed=False 保留所有类别（即使某类别为空）
    len_seg_stats = df.groupby("len_seg", observed=False).agg(
        count=("Comment_ID", "count"),
        avg_sentiment=("Sentiment_Score", "mean"),
        avg_likes=("Liked_Count", "mean")
    ).reset_index()

    enriched["length_segments"] = []
    for _, row in len_seg_stats.iterrows():
        enriched["length_segments"].append({
            "segment": str(row["len_seg"]),
            "count": int(row["count"]),
            "avg_sentiment": round(float(row["avg_sentiment"]), 3),
            "avg_likes": round(float(row["avg_likes"]), 1)
        })

    # ==================================================================
    # 维度 5：月度互动趋势
    # ==================================================================
    # 按年月分组，统计每月的评论量、情感均值、点赞均值/总量/最大值
    print("Analyzing monthly engagement...")
    timeline_df = df.dropna(subset=["Year_Month"])
    monthly_eng = timeline_df.groupby("Year_Month").agg(
        comment_count=("Comment_ID", "count"),       # 评论量
        avg_sentiment=("Sentiment_Score", "mean"),   # 平均情感分
        avg_likes=("Liked_Count", "mean"),           # 平均点赞数
        total_likes=("Liked_Count", "sum"),          # 总点赞数
        max_likes=("Liked_Count", "max")             # 当月最高点赞
    ).reset_index().sort_values("Year_Month")

    enriched["monthly_engagement"] = []
    for _, row in monthly_eng.iterrows():
        enriched["monthly_engagement"].append({
            "year_month": str(row["Year_Month"]),
            "comment_count": int(row["comment_count"]),
            "avg_sentiment": round(float(row["avg_sentiment"]), 3),
            "avg_likes": round(float(row["avg_likes"]), 1),
            "total_likes": int(row["total_likes"]),
            "max_likes": int(row["max_likes"])
        })

    # ==================================================================
    # 维度 6：峰值时刻
    # ==================================================================
    # 找出评论量最高和情感值最高的月份
    peak_activity = max(monthly_eng.iterrows(), key=lambda x: x[1]["comment_count"])
    peak_sentiment = max(monthly_eng.iterrows(), key=lambda x: x[1]["avg_sentiment"])
    enriched["peak_moments"] = {
        "peak_activity_month": str(peak_activity[1]["Year_Month"]),
        "peak_activity_count": int(peak_activity[1]["comment_count"]),
        "peak_sentiment_month": str(peak_sentiment[1]["Year_Month"]),
        "peak_sentiment_value": round(float(peak_sentiment[1]["avg_sentiment"]), 3)
    }

    # ==================================================================
    # 维度 7：精选评论（分维度选取代表性评论）
    # ==================================================================
    print("Selecting featured comments...")

    def pick_top(df_sub, n=8):
        """从子集中选取点赞数最高的 n 条评论"""
        return df_sub.nlargest(n, "Liked_Count")[
            ["Comment_ID", "Nickname", "Content", "Liked_Count",
             "Sentiment_Score", "Sentiment_Class", "Time_String"]
        ].to_dict(orient="records")

    enriched["featured_comments"] = {
        "most_liked": clean_records(pick_top(df, 10)),                              # 全站最高赞
        "most_positive": clean_records(pick_top(df[df["Sentiment_Class"] == "积极"], 8)),  # 最积极
        "most_touching": clean_records(pick_top(df[df["Sentiment_Class"] == "消极"], 8)),  # 最感性
        "long_stories": clean_records(                                              # 长篇故事
            df[df["Content"].apply(len) > 60].nlargest(8, "Liked_Count")[
                ["Comment_ID", "Nickname", "Content", "Liked_Count",
                 "Sentiment_Score", "Sentiment_Class", "Time_String"]
            ].to_dict(orient="records")
        )
    }

    # ==================================================================
    # 维度 8：情感变化速度（环比变化量）
    # ==================================================================
    # 计算相邻月份的 avg_sentiment 差值，反映情感走势的加速度
    print("Calculating sentiment velocity...")
    sentiment_velocity = []
    prev_sent = None
    for _, row in monthly_eng.iterrows():
        cur_sent = float(row["avg_sentiment"])
        delta = round(cur_sent - prev_sent, 3) if prev_sent is not None else 0
        sentiment_velocity.append({
            "year_month": str(row["Year_Month"]),
            "sentiment": round(cur_sent, 3),
            "delta": delta  # 正值=上升，负值=下降
        })
        prev_sent = cur_sent
    enriched["sentiment_velocity"] = sentiment_velocity

    # ==================================================================
    # 维度 9：词语共现网络分析
    # ==================================================================
    # 选取 8 个核心情感词，计算它们在同一评论中共同出现的关联强度。
    # 使用三个关联指标：
    #   - Jaccard 系数：交集/并集，衡量共现概率
    #   - NPMI（标准化点互信息）：[-1, 1]，衡量相关性方向
    #   - Phi 系数：[-1, 1]，二元变量相关系数
    print("Analyzing word co-occurrence...")
    target_words = ["回忆", "眼泪", "幸福", "遗憾", "爱情", "时光", "孤独", "希望"]
    total_docs = len(df)

    # 统计每个词的出现次数和词对共现次数
    co_occurrence = defaultdict(lambda: defaultdict(int))
    word_doc_counts = defaultdict(int)

    for text in df["Content"]:
        text_str = str(text)
        # 找出当前评论中包含的目标词
        present = [w for w in target_words if w in text_str]
        for w in present:
            word_doc_counts[w] += 1
        # 两两配对计数
        for i, w1 in enumerate(present):
            for w2 in present[i + 1:]:
                co_occurrence[w1][w2] += 1
                co_occurrence[w2][w1] += 1

    # 计算词对之间的关联指标
    co_occur_links = []
    for w1 in target_words:
        for w2 in target_words:
            if w1 >= w2:
                continue  # 只处理上三角，避免重复

            a = co_occurrence[w1][w2]  # 两个词同时出现
            if a == 0:
                continue  # 没有共现则跳过

            b = word_doc_counts[w1] - a  # 仅 w1 出现
            c = word_doc_counts[w2] - a  # 仅 w2 出现
            d = total_docs - word_doc_counts[w1] - word_doc_counts[w2] + a  # 都不出现

            # ---- Jaccard 相似度 ----
            union = word_doc_counts[w1] + word_doc_counts[w2] - a
            jaccard = round(a / union, 4) if union > 0 else 0.0

            # ---- NPMI（标准化点互信息）----
            p_w1 = word_doc_counts[w1] / total_docs
            p_w2 = word_doc_counts[w2] / total_docs
            p_joint = a / total_docs
            if p_joint > 0 and p_w1 > 0 and p_w2 > 0:
                pmi = np.log(p_joint / (p_w1 * p_w2))
                npmi = round(pmi / (-np.log(p_joint)), 4)
            else:
                npmi = 0.0

            # ---- Phi 系数（二元相关系数）----
            phi_denom = (a + b) * (c + d) * (a + c) * (b + d)
            phi = round((a * d - b * c) / np.sqrt(phi_denom), 4) if phi_denom > 0 else 0.0

            co_occur_links.append({
                "source": w1,
                "target": w2,
                "value": a,           # 共现次数
                "jaccard": jaccard,   # Jaccard 系数
                "npmi": npmi,         # 标准化点互信息
                "phi": phi            # Phi 相关系数
            })

    enriched["word_co_occurrence"] = {
        "nodes": [{"name": w, "total": word_doc_counts[w]} for w in target_words],
        "links": co_occur_links
    }

    # ==================================================================
    # 维度 10：年度对比
    # ==================================================================
    # 按年份聚合，对比不同年份的评论量和情感变化
    print("Building year comparison...")
    yearly = df.dropna(subset=["Year_Month"]).copy()
    yearly["Datetime"] = pd.to_datetime(yearly["Datetime"], errors="coerce")
    yearly["Year"] = yearly["Datetime"].dt.year
    year_comparison = yearly.groupby("Year").agg(
        comment_count=("Comment_ID", "count"),
        avg_sentiment=("Sentiment_Score", "mean"),
        avg_likes=("Liked_Count", "mean")
    ).reset_index()

    enriched["year_comparison"] = []
    for _, row in year_comparison.iterrows():
        enriched["year_comparison"].append({
            "year": int(row["Year"]),
            "comment_count": int(row["comment_count"]),
            "avg_sentiment": round(float(row["avg_sentiment"]), 3),
            "avg_likes": round(float(row["avg_likes"]), 1)
        })

    # ==================================================================
    # 维度 11：叙事统计摘要
    # ==================================================================
    # 汇总关键指标，用于前端 Hero 区域和结尾 Outro 展示
    total_comments = len(df)
    unique_users = df["User_ID"].nunique() if "User_ID" in df.columns else 0
    total_likes = int(df["Liked_Count"].sum())
    avg_len = float(df["Content"].apply(len).mean())

    enriched["narrative_stats"] = {
        "total_comments": total_comments,
        "unique_users": int(unique_users),
        "total_likes": total_likes,
        "avg_length": round(avg_len, 1),
        "positive_pct": round(float((df["Sentiment_Class"] == "积极").sum() / total_comments * 100), 1),
        "time_span": f"{df['Year_Month'].dropna().min()} ~ {df['Year_Month'].dropna().max()}",
        "night_owl_pct": enriched.get("night_owl_ratio", 0),
        "avg_sentiment": round(float(df["Sentiment_Score"].mean()), 3)
    }

    # ==================================================================
    # 输出：写入 JSON 文件
    # ==================================================================
    output_path = os.path.join(SCRIPT_DIR, "enriched_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)
    print(f"[Done] Enriched data written to: {output_path}")
    print(f"  Keys: {list(enriched.keys())}")


if __name__ == "__main__":
    main()
