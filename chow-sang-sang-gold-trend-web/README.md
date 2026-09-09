# 周生生两地金价趋势

一个零依赖的静态网页，用于比较香港与中国大陆周生生足金饰品挂牌价。

## 功能

- 最近 30 天挂牌价趋势
- 香港价格折算为人民币/克
- 两地相对走势对比
- 大陆价格减香港折算价格的每日价差
- 鼠标悬停查看逐日价格
- 支持桌面和移动端

## 使用

通过本地 HTTP 服务预览：

```bash
python3 -m http.server 8000
```

然后访问 `http://localhost:8000`。页面使用 `fetch` 读取本地 JSON，因此不建议直接通过 `file://` 打开。

部署时可将整个目录的内容发布到 GitHub Pages、GitLab Pages 或任意静态网站托管服务。

## 自动更新

GitHub Actions 每天北京时间约 10:30 运行 `scripts/update_prices.py`，抓取两地报价和港币兑人民币汇率，并更新 `data/prices.json`。也可以在仓库的 **Actions → Update gold prices → Run workflow** 手动执行。

仓库设置需要允许 Actions 写入：**Settings → Actions → General → Workflow permissions → Read and write permissions**。

## 数据口径

- 香港：港币/两除以 37.5，再乘以 0.8558 港币兑人民币换算率；报价含 2% 佣金，不含工费。
- 中国大陆：人民币/克，不含工费。
- 页面展示最近约 30 至 40 天数据，并通过 GitHub Actions 每日更新。

数据仅供展示和研究，不构成投资或购买建议。实际交易价格以周生生门店或官方网站为准。
