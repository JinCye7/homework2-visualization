# 网易云音乐《如果可以》评论情感可视化

## 项目简介

对网易云音乐韦礼安《如果可以》歌曲的 74,384 条评论进行文本分析与情感可视化。包含数据清洗、中文分词、词云生成、LDA 主题聚类、交互式可视化叙事页面。

## 文件结构

```
├── Homework2_Solution_Template.md  # 实验报告（已填写）
├── README.md                       # 本文件
├── code/                           # 源代码
│   ├── crawler.py                  # 网易云评论爬虫
│   ├── step1_clean.py              # 数据清洗
│   ├── step2_tokenize.py           # 中文分词
│   ├── step3_analyze_aggregate.py  # 情感分析 + LDA + 图表生成
│   ├── enrich_data.py              # 深度数据分析
│   ├── sentiment_lexicon.py        # 中文情感词典
│   ├── update_html.py              # HTML 数据注入
│   └── regenerate_all.py           # 一键全流程脚本
├── images/                         # 可视化图表（PNG）
│   ├── comment_length_distribution.png
│   ├── likes_distribution.png
│   ├── wordcloud_all.png
│   ├── wordcloud_highlikes.png
│   ├── wordcloud_normal.png
│   ├── top30_words.png
│   ├── sentiment_pie.png
│   ├── sentiment_timeline.png
│   ├── sentiment_vs_likes.png
│   └── advanced_analysis.png
├── visualization/                  # 交互式可视化页面
│   ├── final_result.html            # 主页面（浏览器打开即可）
│   ├── echarts.min.js
│   ├── echarts-wordcloud.min.js
│   ├── dashboard_data.json
│   └── enriched_data.json
└── data/                           # 数据文件
    ├── cleaning_stats.txt          # 清洗统计
    └── jieba_user_dict.txt         # 自定义分词词库
```

## 运行方式

### 查看可视化结果
直接浏览器打开 `visualization/final_result.html` 即可查看完整的交互式可视化叙事页面。

### 重新生成分析
```bash
cd code
python regenerate_all.py
```
按顺序执行：情感重新打分 → 数据深度分析 → HTML 数据更新。

### 单独运行各步骤
```bash
python step1_clean.py     # 数据清洗
python step2_tokenize.py  # 中文分词
python step3_analyze_aggregate.py  # 情感分析 + 可视化
python enrich_data.py     # 深度分析
```

## 技术栈

- Python: pandas, numpy, jieba, snownlp, scikit-learn, matplotlib, seaborn, wordcloud
- 前端: ECharts, echarts-wordcloud
- 情感分析: 混合模型（55% 自建中文情感词典 + 45% SnowNLP）

## 数据来源

网易云音乐 API · 《如果可以》韦礼安 · 2021-11 至 2026-05
