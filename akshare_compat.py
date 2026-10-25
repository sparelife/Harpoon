# -*- coding: utf-8 -*-
"""akshare 数据源兼容层。

akshare 的 bond_zh_cov_value_analysis 按列位置硬编码了 13 个列名,而东方财富接口
返回的列会追加新字段(如 SECUCODE / FLOORPRICE_PREMIUM_RATIO_CB / BOND_NAME_ABBR),
于是报 "Length mismatch: Expected axis has 15 elements, new values have 13 elements"。

这里改为按字段名取值,接口增删无关列不再影响解析;返回结构与 akshare 原函数一致。
"""

import pandas as pd
import requests

_URL = "https://datacenter-web.eastmoney.com/api/data/get"
_PARAMS = {
    "sty": "ALL",
    "token": "894050c76af8597a853f5b408b759f5d",
    "st": "date",
    "sr": "1",
    "source": "WEB",
    "type": "RPTA_WEB_KZZ_LS",
    "p": "1",
    "ps": "8000",
}

# 东方财富字段名 -> akshare 原有中文列名
_FIELD_MAP = {
    "DATE": "日期",
    "FCLOSE": "收盘价",
    "PUREBONDVALUE": "纯债价值",
    "SWAPVALUE": "转股价值",
    "PUREBONDOR": "纯债溢价率",
    "SWAPOR": "转股溢价率",
}
_NUMERIC_COLS = ["收盘价", "纯债价值", "转股价值", "纯债溢价率", "转股溢价率"]


def bond_zh_cov_value_analysis(symbol="113527"):
	"""可转债价值分析(溢价率分析),symbol 为纯数字代码,如 '113527'。"""
	params = dict(_PARAMS, filter='(zcode="%s")' % symbol)
	r = requests.get(_URL, params=params, timeout=30)
	r.raise_for_status()
	data = r.json()["result"]["data"]
	if not data:
		return pd.DataFrame(columns=list(_FIELD_MAP.values()))

	temp_df = pd.DataFrame(data)
	missing = [f for f in _FIELD_MAP if f not in temp_df.columns]
	if missing:
		raise ValueError("东财价值分析接口缺少字段: " + ", ".join(missing))

	temp_df = temp_df[list(_FIELD_MAP)].rename(columns=_FIELD_MAP)
	for col in _NUMERIC_COLS:
		temp_df[col] = pd.to_numeric(temp_df[col], errors="coerce")
	temp_df["日期"] = pd.to_datetime(temp_df["日期"], errors="coerce").dt.date
	return temp_df[["日期"] + _NUMERIC_COLS]
