# SQL与Python分析

## 已生成的结果

[实际SQL](analysis.sql) · [汇总CSV](../02-data/summary/) · [SQL截图](../04-dashboard/images/sql-results.png)

分析包括：9字段去重、整数分金额存储、同用户同会话同商品的浏览后购买路径、完整观察窗口Cohort回访、正价购买用户RFM规则分层。分群人数和金额、事件与日汇总、留存分母都做过核对。

## 复算顺序

需要Python 3及numpy。以下命令从仓库根目录执行：

```bash
python -m pip install -r 03-analysis/requirements.txt
python 03-analysis/scripts/acquire.py
python 03-analysis/scripts/analyze.py
python 03-analysis/scripts/build_dashboard.py
```

获取脚本从REES46官方压缩文件读取至2019年10月15日边界，只保留前14天服饰类事件。需要网络、下载时间及本地空间，不是小文件示例。原始筛选CSV、中间SQLite保存在被忽略的 `02-data/raw/`，汇总写入 `02-data/summary/`，最后一步重新生成 `04-dashboard/index.html`。

`analysis.sql`是此次实际执行的核心SQL，不是独立完整导入器；加载CSV和Python分位数分层由 `scripts/analyze.py` 完成。看板在运行生成脚本后才会刷新。

## 重要口径

服饰子集没有加购事件，不能画成加购转化率0的三步漏斗。D7回访不是注册留存，也不是复购率。F为购买会话数，M为购买事件价格和，没有订单ID、数量、成本和退款，不是净收入。
