# Computed results / 运行结果

这些表格由学术 Notebook 计算生成，不是从网页的统计结果文件复制。`environment.json` 记录运行依赖版本，输入校验和在 `../data/manifest.json`。

| 文件 | 含义 |
|---|---|
| `cohorts.csv` | 各时期、位相的季节数、风暴数、有限九矩样本数 |
| `seasonal_contrasts.csv` | 三项季节活动差：拉尼娜减厄尔尼诺；95% CI；置换 p 与 Holm p |
| `type_rates.csv` | 四类路径年发生率差及其区间与 Holm p |
| `cluster_selection.csv` | K=3–7 的重拟合轮廓系数 |
| `centroid_decomposition.csv` | 厄尔尼诺减拉尼娜的总质心差、构成项、类内项及区间、p 值 |
| `decomposition_robustness.csv` | K=3–7 与去趋势后的效应；空白 CI 表示该敏感性步骤未计算区间 |
| `period_intensity_sensitivity.csv` | 不同时期与强度门槛下的风暴数差 |
| `leave_one_season_out.csv` | 逐季剔除后的质心差点估计 |
| `moment_contrasts.csv` | 九个矩的组间均值差及 BH q |
| `classification.csv` | 六组特征的整年分组 AUC、零分布范围与 BH q |
| `auc_permutation_nulls.csv` | 每组特征的 199 次整年标签置换 AUC |
| `auc_gain_bootstrap.csv` | 200 次配对季节 bootstrap 的 AUC 增益 |
| `classification_config.json` | 分类重采样配置、样本量及增益区间 |
| `claim_evidence.csv` | 本次运行生成的结论—证据对应表 |

季节活动和类型发生率使用 **La Niña − El Niño**；质心与九矩比较使用 **El Niño − La Niña**，与各自科学问题的表述一致。经纬度的变化用度表示，不等同于固定公里距离。
