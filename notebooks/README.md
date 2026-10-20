# Academic analysis / 学术分析

[打开已完整运行的 Notebook](enso_storm_atlas_research.ipynb)

中文正文，英文图表；从研究问题、数据定义和方法公式，到统计结果、稳健性、讨论和结论。输入使用与在线图谱相同的固定快照，不从已有网页统计结果读取答案。

## Run

在仓库根目录执行（已验证 Python 3.13）：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS / Linux: source .venv/bin/activate
pip install -r requirements-notebook.txt
python scripts/run_research_notebook.py
python scripts/check_research_notebook.py
```

运行器使用当前 Python 环境启动空内核，顺序执行所有代码单元，成功后保存结果。它不读取旧的单元输出。第一次运行需要安装依赖；之后分析和绘图不需要联网，也不要求下载 50 MB 以上的原始路径档案。分类置换与配对 bootstrap 是主要耗时步骤，运行时间取决于电脑性能。最后一条命令独立检查单元执行状态、输入校验和、图表输出、分解恒等式、FDR 校正和区间一致性。

要匹配本次主要依赖版本，可使用根目录的 `requirements-notebook-lock.txt`；实际执行环境记录在 `results/environment.json`。Notebook 也可用 JupyterLab / VS Code 打开后从头运行。启动位置应为仓库根目录或 `notebooks/`。

## Files

| 路径 | 内容 |
|---|---|
| `enso_storm_atlas_research.ipynb` | 完整研究叙述、可执行代码、图表与结果 |
| `atlas_analysis.py` | 季节分组统计与绘图函数 |
| `data/atlas_snapshot.json` | 1950–2025 固定处理后数据；979 条路径 |
| `data/manifest.json` | 来源、源代码提交及 SHA-256 校验和 |
| `data/atlantic_land.geojson` | 制图用海岸线 |
| `figures/` | 图 1–7：每张提供 PNG、PDF、SVG |
| `results/` | 效应量、区间、p/q 值、分类零分布、bootstrap 样本及环境信息 |

`../scripts/build_research_notebook.py` 是 Notebook 的叙述和单元生成源文件；只有需要重新生成单元结构时才运行，它会清空已保存输出。通常直接运行 `run_research_notebook.py` 即可。

## Statistical scope

- 主窗口：1966–2025；中性年用于背景展示，主要位相对比为 14 个拉尼娜年和 15 个厄尔尼诺年。
- 置换和 bootstrap 均以整年为单位；类型构成分解满足精确加和恒等式。
- 活动指标、类型发生率、分解分量进行分组 Holm 校正；矩与分类特征比较报告 BH q 值。
- 分类每折内拟合标准化；同一年、同一年重复抽中的副本不会跨训练和测试。
- 图中 AUC 灰条表示打乱标签的 5–95% 零分布范围，不是观察 AUC 的置信区间。
- 高阶矩增益的区间来自配对季节 bootstrap；不同随机分折不被当作独立样本。

网站和 Notebook 共享数据、主要效应定义和观察 AUC。Notebook 使用更多置换、显式区间和多重比较校正，因此部分 p 值和区间与网页有所不同。代码不会改写网站的统计数据。
