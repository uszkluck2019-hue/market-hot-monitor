#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日市场数据综合更新脚本（云端版）
整合所有数据抓取逻辑，输出 data.json 和 market_stats.json 到当前目录
"""

import os
import sys
import logging
import traceback
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────── 日志配置 ───────────────────────
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "update_stats.log")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("fetch_all")
# ─────────────────────── 日志配置 ───────────────────────

# 导入工具模块
sys.path.insert(0, SCRIPT_DIR)
from data_utils import load_data, save_data, get_mood

DATA_FILE = os.path.join(SCRIPT_DIR, "data.json")
STATS_FILE = os.path.join(SCRIPT_DIR, "market_stats.json")

# ─────────────────────── 财联社热度 ───────────────────────

def fetch_cls_heat():
    """使用 Playwright 自动获取财联社热度"""
    try:
        from playwright.sync_api import sync_playwright
        import re

        heat_value = None
        turnover_value = None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.cls.cn/finance", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            text = page.evaluate('() => document.body.innerText')
            browser.close()

        match = re.search(r'(\d{1,2})\.?\d*\s*[°°]?\s*市场热度', text)
        if match:
            heat_value = match.group(1)

        match = re.search(r'(\d+\.?\d*)\s*万亿', text)
        if match:
            turnover_value = float(match.group(1))

        return heat_value, turnover_value
    except Exception as e:
        logger.warning(f"财联社热度获取失败: {e}")
        return None, None


# ─────────────────────── 拥挤度 ───────────────────────

def fetch_congestion():
    """使用 Playwright 从 legulegu.com 获取拥挤度"""
    try:
        from playwright.sync_api import sync_playwright
        import re

        congestion_value = None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1920, "height": 1080})
            page.goto("https://legulegu.com/stockdata/ashares-congestion",
                     wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            text = page.evaluate('() => document.body.innerText')
            browser.close()

        match = re.search(r'(\d{1,2}\.\d{1,2})%', text)
        if match:
            congestion_value = float(match.group(1))
        else:
            percentages = re.findall(r'(\d+\.?\d*)%', text)
            for p in percentages:
                val = float(p)
                if 10 <= val <= 80:
                    congestion_value = val
                    break

        return congestion_value
    except Exception as e:
        logger.warning(f"拥挤度获取失败: {e}")
        return None


# ─────────────────────── 总市值/GDP ───────────────────────

def fetch_market_gdp():
    """使用 Playwright 从 legulegu.com 获取总市值/GDP"""
    try:
        from playwright.sync_api import sync_playwright
        import re

        ratio = None

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": 1920, "height": 1080})
            page.goto("https://legulegu.com/stockdata/marketcap-gdp",
                     wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            text = page.evaluate('() => document.body.innerText')
            browser.close()

        match = re.search(r"总市值/GDP:\s*([\d.]+)%", text)
        if match:
            ratio = float(match.group(1))

        return ratio
    except Exception as e:
        logger.warning(f"总市值/GDP 获取失败: {e}")
        return None


# ─────────────────────── 股债利差 ───────────────────────

def fetch_equity_bond_spread():
    """使用 akshare 获取沪深300 PE 和 10年国债收益率"""
    try:
        import akshare as ak
        import pandas as pd

        df_pe = ak.stock_zh_index_value_csindex(symbol="000300")
        df_pe = df_pe[["日期", "市盈率1", "股息率1"]].copy()
        df_pe.columns = ["date", "pe", "dividend_yield"]
        df_pe["date"] = pd.to_datetime(df_pe["date"])
        df_pe["pe"] = pd.to_numeric(df_pe["pe"], errors="coerce")
        df_pe = df_pe.dropna(subset=["date", "pe"])

        df_bond = ak.bond_zh_us_rate()
        df_bond = df_bond[["日期", "中国国债收益率10年"]].copy()
        df_bond.columns = ["date", "bond_yield"]
        df_bond["date"] = pd.to_datetime(df_bond["date"])
        df_bond["bond_yield"] = pd.to_numeric(df_bond["bond_yield"], errors="coerce")
        df_bond = df_bond.dropna(subset=["date", "bond_yield"])

        merged = pd.merge(df_pe, df_bond, on="date", how="inner")
        merged = merged.sort_values("date", ascending=False).reset_index(drop=True)

        if merged.empty:
            return None

        latest = merged.iloc[0]
        earnings_yield = (1 / latest["pe"] * 100)
        spread = earnings_yield - latest["bond_yield"]

        return round(float(spread), 4)
    except Exception as e:
        logger.warning(f"股债利差获取失败: {e}")
        return None


# ─────────────────────── 主流程 ───────────────────────

def main():
    start = datetime.now()
    logger.info(f"🚀 每日市场数据更新开始: {start.strftime('%Y-%m-%d %H:%M')}")

    # 读取现有数据
    data = load_data()
    today = datetime.now().strftime('%Y-%m-%d')

    # 1. 财联社热度和成交额
    try:
        heat_str, turnover = fetch_cls_heat()
        if heat_str:
            heat = float(heat_str)
            found = False
            for item in data["market_heat"]:
                if item["date"] == today:
                    item["heat"] = heat
                    item["amount"] = turnover if turnover else item.get("amount", 0)
                    item["mood"] = get_mood(heat)
                    found = True
                    break
            if not found:
                data["market_heat"].append({
                    "date": today,
                    "heat": heat,
                    "amount": turnover if turnover else 0,
                    "mood": get_mood(heat)
                })
            logger.info(f"✅ 财联社热度: {heat} ({get_mood(heat)})")
        else:
            logger.warning("⚠️ 财联社热度获取失败，跳过")
    except Exception as e:
        logger.warning(f"⚠️ 财联社步骤异常: {e}")

    # 2. 拥挤度
    try:
        congestion = fetch_congestion()
        if congestion:
            data["stats"]["congestion"] = congestion
            logger.info(f"✅ 拥挤度: {congestion}%")
        else:
            logger.warning("⚠️ 拥挤度获取失败，跳过")
    except Exception as e:
        logger.warning(f"⚠️ 拥挤度步骤异常: {e}")

    # 3. 总市值/GDP
    try:
        gdp = fetch_market_gdp()
        if gdp:
            data["stats"]["gdp"] = round(gdp, 2)
            logger.info(f"✅ 总市值/GDP: {gdp}%")
        else:
            logger.warning("⚠️ 总市值/GDP获取失败，跳过")
    except Exception as e:
        logger.warning(f"⚠️ 总市值/GDP步骤异常: {e}")

    # 4. 股债利差
    try:
        spread = fetch_equity_bond_spread()
        if spread:
            data["stats"]["spread"] = spread
            logger.info(f"✅ 股债利差: {spread}%")
        else:
            logger.warning("⚠️ 股债利差获取失败，跳过")
    except Exception as e:
        logger.warning(f"⚠️ 股债利差步骤异常: {e}")

    # 更新时间
    data["stats"]["update_time"] = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 写 data.json
    save_data(data)
    logger.info(f"✅ data.json 已更新 (共 {len(data['market_heat'])} 条记录)")

    # 写 market_stats.json
    stats_data = {
        "stats": {
            "congestion": data["stats"].get("congestion", 0),
            "gdp": data["stats"].get("gdp", 0),
            "spread": data["stats"].get("spread", 0),
            "update_time": data["stats"]["update_time"]
        }
    }
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        import json
        json.dump(stats_data, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ market_stats.json 已更新")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"📊 更新完成，耗时 {elapsed:.1f}s")


if __name__ == "__main__":
    main()