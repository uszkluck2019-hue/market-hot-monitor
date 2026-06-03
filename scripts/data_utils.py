#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据读写工具 - 统一管理 data.json
"""

import json
import os
from datetime import datetime

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def load_data():
    """读取 JSON 数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"market_heat": [], "stats": {}}


def save_data(data):
    """保存 JSON 数据"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_mood(heat):
    """根据热度值返回状态"""
    if heat >= 80:
        return "极热"
    if heat >= 65:
        return "过热"
    if heat >= 50:
        return "热"
    if heat >= 40:
        return "温"
    if heat >= 22:
        return "寒"
    return "极寒"


if __name__ == "__main__":
    print("数据工具模块")