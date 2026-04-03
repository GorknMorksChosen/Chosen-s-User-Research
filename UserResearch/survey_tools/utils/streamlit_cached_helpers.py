"""Streamlit 缓存封装：供 Web 入口对读表与 sklearn 拟合做 ttl 缓存，减轻重复计算。"""

from __future__ import annotations

import io
from typing import Union

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor

from survey_tools.utils.io import load_sav, read_table_auto


@st.cache_data(ttl=3600)
def cached_read_table_bytes(
    file_bytes: bytes,
    filename_lower: str,
    sheet_name: Union[int, str],
) -> pd.DataFrame:
    """从上传字节读取 CSV / Excel（扩展名由 filename_lower 推断）。"""
    bio = io.BytesIO(file_bytes)
    bio.name = filename_lower
    df = read_table_auto(bio, sheet_name=sheet_name)
    df.columns = [str(c).strip() for c in df.columns]
    return df


@st.cache_data(ttl=3600)
def cached_load_sav_bytes(file_bytes: bytes) -> tuple[pd.DataFrame, dict, dict]:
    """缓存 pyreadstat 读取 .sav 的完整结果（含标签）。"""
    bio = io.BytesIO(file_bytes)
    bio.name = "upload.sav"
    return load_sav(bio)


@st.cache_resource(ttl=3600)
def cached_kmeans_fit(
    scaled_data: np.ndarray,
    n_clusters: int,
    random_state: int = 42,
) -> KMeans:
    """对固定随机种子的 KMeans 拟合结果做资源级缓存。"""
    km = KMeans(n_clusters=n_clusters, random_state=random_state)
    km.fit(scaled_data)
    return km


@st.cache_resource(ttl=3600)
def cached_rf_fit(
    X: np.ndarray,
    y: np.ndarray,
    feature_order: tuple[str, ...],  # noqa: ARG001 — 仅参与 Streamlit 缓存键
    n_estimators: int = 100,
    random_state: int = 42,
) -> RandomForestRegressor:
    """随机森林拟合缓存；feature_order 参与缓存键以区分列集合与顺序。"""
    model = RandomForestRegressor(n_estimators=n_estimators, random_state=random_state)
    model.fit(X, y)
    return model
