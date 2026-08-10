"""
Data formatting utilities for converting pandas DataFrames to JSON responses.

All MCP tool responses are returned as JSON strings for Claude to parse.

Design principle: return compact, LLM-friendly data — not raw database dumps.
  - Financial statements: whitelist key fields, rename to Chinese, convert to 亿元
  - General data: drop all-null columns, remove internal codes / QoQ bloat
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd


# ──────────────────────────────────────────────────────────────────
# Financial Statement Column Whitelists
#
# Each entry: (raw_EM_column, display_name, convert_to_亿)
#   - raw_EM_column: column name from 东方财富 API
#   - display_name: clean Chinese name for LLM
#   - convert_to_亿: if True, divide value by 1e8 and round to 2 decimals
# ──────────────────────────────────────────────────────────────────

INCOME_STATEMENT_COLS: list[tuple[str, str, bool]] = [
    ("REPORT_DATE_NAME", "报告期", False),
    ("TOTAL_OPERATE_INCOME", "营业总收入(亿)", True),
    ("OPERATE_INCOME", "营业收入(亿)", True),
    ("OPERATE_COST", "营业成本(亿)", True),
    ("SALE_EXPENSE", "销售费用(亿)", True),
    ("MANAGE_EXPENSE", "管理费用(亿)", True),
    ("RESEARCH_EXPENSE", "研发费用(亿)", True),
    ("FINANCE_EXPENSE", "财务费用(亿)", True),
    ("FE_INTEREST_EXPENSE", "财务费用-利息费用(亿)", True),
    ("FE_INTEREST_INCOME", "财务费用-利息收入(亿)", True),
    ("OPERATE_TAX_ADD", "营业税金及附加(亿)", True),
    ("ASSET_IMPAIRMENT_LOSS", "资产减值损失(亿)", True),
    ("CREDIT_IMPAIRMENT_LOSS", "信用减值损失(亿)", True),
    ("OTHER_INCOME", "其他收益(亿)", True),
    ("INVEST_INCOME", "投资收益(亿)", True),
    ("INVEST_JOINT_INCOME", "对合营联营企业投资收益(亿)", True),
    ("FAIRVALUE_CHANGE_INCOME", "公允价值变动收益(亿)", True),
    ("ASSET_DISPOSAL_INCOME", "资产处置收益(亿)", True),
    ("NONBUSINESS_INCOME", "营业外收入(亿)", True),
    ("NONBUSINESS_EXPENSE", "营业外支出(亿)", True),
    ("OPERATE_PROFIT", "营业利润(亿)", True),
    ("TOTAL_PROFIT", "利润总额(亿)", True),
    ("INCOME_TAX", "所得税费用(亿)", True),
    ("NETPROFIT", "净利润(亿)", True),
    ("PARENT_NETPROFIT", "归母净利润(亿)", True),
    ("DEDUCT_PARENT_NETPROFIT", "扣非归母净利润(亿)", True),
    ("MINORITY_INTEREST", "少数股东损益(亿)", True),
    ("CONTINUED_NETPROFIT", "持续经营净利润(亿)", True),
    ("DISCONTINUED_NETPROFIT", "终止经营净利润(亿)", True),
    ("TOTAL_COMPRE_INCOME", "综合收益总额(亿)", True),
    ("PARENT_TCI", "归母综合收益(亿)", True),
    ("BASIC_EPS", "基本每股收益(元)", False),
    ("DILUTED_EPS", "稀释每股收益(元)", False),
]

BALANCE_SHEET_COLS: list[tuple[str, str, bool]] = [
    ("REPORT_DATE_NAME", "报告期", False),
    ("MONETARYFUNDS", "货币资金(亿)", True),
    ("ACCOUNTS_RECE", "应收账款(亿)", True),
    ("PREPAYMENT", "预付款项(亿)", True),
    ("INVENTORY", "存货(亿)", True),
    ("TRADE_FINASSET", "交易性金融资产(亿)", True),
    ("NOTE_RECE", "应收票据(亿)", True),
    ("NOTE_ACCOUNTS_RECE", "应收票据及应收账款(亿)", True),
    ("CONTRACT_ASSET", "合同资产(亿)", True),
    ("FINANCE_RECE", "应收款项融资(亿)", True),
    ("OTHER_RECE", "其他应收款(亿)", True),
    ("DIVIDEND_RECE", "应收股利(亿)", True),
    ("INTEREST_RECE", "应收利息(亿)", True),
    ("OTHER_CURRENT_ASSET", "其他流动资产(亿)", True),
    ("TOTAL_CURRENT_ASSETS", "流动资产合计(亿)", True),
    ("FIXED_ASSET", "固定资产(亿)", True),
    ("CIP", "在建工程(亿)", True),
    ("INTANGIBLE_ASSET", "无形资产(亿)", True),
    ("GOODWILL", "商誉(亿)", True),
    ("LONG_EQUITY_INVEST", "长期股权投资(亿)", True),
    ("INVEST_REALESTATE", "投资性房地产(亿)", True),
    ("USERIGHT_ASSET", "使用权资产(亿)", True),
    ("DEVELOP_EXPENSE", "开发支出(亿)", True),
    ("LONG_PREPAID_EXPENSE", "长期待摊费用(亿)", True),
    ("DEFER_TAX_ASSET", "递延所得税资产(亿)", True),
    ("OTHER_NONCURRENT_ASSET", "其他非流动资产(亿)", True),
    ("TOTAL_NONCURRENT_ASSETS", "非流动资产合计(亿)", True),
    ("TOTAL_ASSETS", "总资产(亿)", True),
    ("SHORT_LOAN", "短期借款(亿)", True),
    ("ACCOUNTS_PAYABLE", "应付账款(亿)", True),
    ("NOTE_PAYABLE", "应付票据(亿)", True),
    ("NOTE_ACCOUNTS_PAYABLE", "应付票据及应付账款(亿)", True),
    ("ADVANCE_RECEIVABLES", "预收款项(亿)", True),
    ("STAFF_SALARY_PAYABLE", "应付职工薪酬(亿)", True),
    ("TAX_PAYABLE", "应交税费(亿)", True),
    ("OTHER_PAYABLE", "其他应付款(亿)", True),
    ("OTHER_CURRENT_LIAB", "其他流动负债(亿)", True),
    ("CONTRACT_LIAB", "合同负债(亿)", True),
    ("TOTAL_CURRENT_LIAB", "流动负债合计(亿)", True),
    ("LONG_LOAN", "长期借款(亿)", True),
    ("NONCURRENT_LIAB_1YEAR", "一年内到期的非流动负债(亿)", True),
    ("LEASE_LIAB", "租赁负债(亿)", True),
    ("BOND_PAYABLE", "应付债券(亿)", True),
    ("DEFER_TAX_LIAB", "递延所得税负债(亿)", True),
    ("PREDICT_LIAB", "预计负债(亿)", True),
    ("OTHER_NONCURRENT_LIAB", "其他非流动负债(亿)", True),
    ("TOTAL_NONCURRENT_LIAB", "非流动负债合计(亿)", True),
    ("TOTAL_LIABILITIES", "总负债(亿)", True),
    ("TOTAL_PARENT_EQUITY", "归母股东权益(亿)", True),
    ("SHARE_CAPITAL", "股本(亿)", True),
    ("CAPITAL_RESERVE", "资本公积(亿)", True),
    ("SURPLUS_RESERVE", "盈余公积(亿)", True),
    ("UNASSIGN_RPOFIT", "未分配利润(亿)", True),
    ("OTHER_COMPRE_INCOME", "其他综合收益(亿)", True),
    ("TREASURY_SHARES", "库存股(亿)", True),
    ("PERPETUAL_BOND", "永续债(亿)", True),
    ("MINORITY_EQUITY", "少数股东权益(亿)", True),
    ("TOTAL_EQUITY", "股东权益合计(亿)", True),
    ("TOTAL_LIAB_EQUITY", "负债和股东权益合计(亿)", True),
]

CASHFLOW_STATEMENT_COLS: list[tuple[str, str, bool]] = [
    ("REPORT_DATE_NAME", "报告期", False),
    ("TOTAL_OPERATE_INFLOW", "经营活动现金流入(亿)", True),
    ("SALES_SERVICES", "销售商品提供劳务收到的现金(亿)", True),
    ("RECEIVE_TAX_REFUND", "收到的税费返还(亿)", True),
    ("RECEIVE_OTHER_OPERATE", "收到其他与经营活动有关的现金(亿)", True),
    ("TOTAL_OPERATE_OUTFLOW", "经营活动现金流出(亿)", True),
    ("BUY_SERVICES", "购买商品接受劳务支付的现金(亿)", True),
    ("PAY_STAFF_CASH", "支付给职工的现金(亿)", True),
    ("PAY_ALL_TAX", "支付的各项税费(亿)", True),
    ("PAY_OTHER_OPERATE", "支付其他与经营活动有关的现金(亿)", True),
    ("NETCASH_OPERATE", "经营活动现金流净额(亿)", True),
    ("TOTAL_INVEST_INFLOW", "投资活动现金流入(亿)", True),
    ("WITHDRAW_INVEST", "收回投资收到的现金(亿)", True),
    ("RECEIVE_INVEST_INCOME", "取得投资收益收到的现金(亿)", True),
    ("DISPOSAL_LONG_ASSET", "处置长期资产收回现金净额(亿)", True),
    ("TOTAL_INVEST_OUTFLOW", "投资活动现金流出(亿)", True),
    ("CONSTRUCT_LONG_ASSET", "购建长期资产支付的现金(亿)", True),
    ("INVEST_PAY_CASH", "投资支付的现金(亿)", True),
    ("NETCASH_INVEST", "投资活动现金流净额(亿)", True),
    ("TOTAL_FINANCE_INFLOW", "筹资活动现金流入(亿)", True),
    ("RECEIVE_LOAN_CASH", "取得借款收到的现金(亿)", True),
    ("ISSUE_BOND", "发行债券收到的现金(亿)", True),
    ("TOTAL_FINANCE_OUTFLOW", "筹资活动现金流出(亿)", True),
    ("PAY_DEBT_CASH", "偿还债务支付的现金(亿)", True),
    ("ASSIGN_DIVIDEND_PORFIT", "分配股利或偿付利息支付的现金(亿)", True),
    ("NETCASH_FINANCE", "筹资活动现金流净额(亿)", True),
    ("CCE_ADD", "现金净增加额(亿)", True),
    ("RATE_CHANGE_EFFECT", "汇率变动对现金的影响(亿)", True),
    ("BEGIN_CCE", "期初现金余额(亿)", True),
    ("END_CCE", "期末现金余额(亿)", True),
    ("BEGIN_CASH_EQUIVALENTS", "期初现金及现金等价物(亿)", True),
    ("END_CASH_EQUIVALENTS", "期末现金及现金等价物(亿)", True),
    ("FA_IR_DEPR", "折旧(固定资产/油气/生物资产)(亿)", True),
    ("IR_DEPR", "无形资产摊销(亿)", True),
    ("IA_AMORTIZE", "长期待摊费用摊销(亿)", True),
]


# ──────────────────────────────────────────────────────────────────
# Slim functions — make DataFrames compact for LLM consumption
# ──────────────────────────────────────────────────────────────────

def slim_financial_df(
    df: pd.DataFrame,
    whitelist: list[tuple[str, str, bool]],
) -> pd.DataFrame:
    """
    Slim a raw 东方财富 financial statement DataFrame for LLM consumption.

    1. Select only whitelisted columns (analyst-relevant fields)
    2. Rename English columns to clean Chinese display names
    3. Convert monetary values to 亿元 (÷ 1e8) and round to 2 decimals
    4. Drop columns that are all-null for this particular company

    Args:
        df: Raw DataFrame from akshare EM financial API.
        whitelist: List of (raw_col, display_name, convert_to_yi) tuples.

    Returns:
        Compact DataFrame ready for df_to_json().
    """
    if df is None or df.empty:
        return df

    # Build column name lookup (case-insensitive)
    col_map = {c.upper(): c for c in df.columns}

    result = {}
    for raw_col, display_name, to_yi in whitelist:
        actual_col = col_map.get(raw_col.upper())
        if actual_col is None:
            continue
        col_data = df[actual_col].copy()
        if col_data.isna().all():
            continue

        if to_yi:
            col_data = pd.to_numeric(col_data, errors="coerce") / 1e8
            col_data = col_data.round(2)
        else:
            # Round non-monetary numeric columns for cleanliness
            if pd.api.types.is_numeric_dtype(col_data):
                col_data = col_data.round(4)

        result[display_name] = col_data.values

    if not result:
        # Whitelist matched nothing — fall back to general cleanup
        return slim_df(df)

    return pd.DataFrame(result)


def slim_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    General-purpose cleanup for any DataFrame before sending to LLM.

    1. Drop all-null columns
    2. Drop internal/metadata columns (codes, org info, etc.)
    3. Drop *_QOQ columns (环比/同比) that double the field count

    Args:
        df: Any DataFrame from akshare.

    Returns:
        Cleaned DataFrame.
    """
    if df is None or df.empty:
        return df

    # Drop all-null columns
    df = df.dropna(axis=1, how="all")

    # Internal metadata columns to drop (case-insensitive match)
    _JUNK_EXACT = {
        "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR",
        "ORG_CODE", "ORG_TYPE", "SECURITY_TYPE_CODE",
        "NOTICE_DATE", "UPDATE_DATE", "CURRENCY",
        "OPINION_TYPE", "OSOPINION_TYPE",
    }
    drop_exact = [c for c in df.columns if c.upper() in _JUNK_EXACT]

    # Drop *_QOQ columns (quarter-over-quarter that bloat the response)
    drop_qoq = [c for c in df.columns if c.upper().endswith("_QOQ")]

    all_drop = set(drop_exact + drop_qoq)
    if all_drop:
        df = df.drop(columns=list(all_drop), errors="ignore")

    return df


# ──────────────────────────────────────────────────────────────────
# Core serializers
# ──────────────────────────────────────────────────────────────────

def df_to_json(
    df: pd.DataFrame,
    orient: str = "records",
    max_rows: int | None = None,
    date_format: str = "iso",
) -> str:
    """
    Convert a pandas DataFrame to a JSON string suitable for MCP tool response.

    Automatically drops all-null columns to keep output compact.

    Args:
        df: The DataFrame to convert.
        orient: pandas to_json orient parameter. Default 'records' for list of dicts.
        max_rows: Maximum number of rows to include. None for all.
        date_format: Date format for datetime columns.

    Returns:
        JSON string representation of the DataFrame.
    """
    if df is None or df.empty:
        return json.dumps([], ensure_ascii=False)

    # Always drop all-null columns for cleaner output
    df = df.dropna(axis=1, how="all")

    if max_rows is not None and len(df) > max_rows:
        df = df.head(max_rows)

    # Convert datetime columns to string to avoid serialization issues
    for col in df.select_dtypes(include=["datetime64", "datetimetz"]).columns:
        df[col] = df[col].astype(str)

    return df.to_json(orient=orient, force_ascii=False, date_format=date_format)


def dict_to_json(data: dict[str, Any] | list[dict[str, Any]]) -> str:
    """
    Convert a dict or list of dicts to a JSON string.

    Args:
        data: Dictionary or list of dictionaries to convert.

    Returns:
        JSON string.
    """
    return json.dumps(data, ensure_ascii=False, default=str)


def error_response(message: str, tool_name: str = "") -> str:
    """
    Create a standardized error response JSON string.

    Args:
        message: Error description.
        tool_name: Name of the tool that errored.

    Returns:
        JSON string with error info.
    """
    return json.dumps(
        {
            "error": True,
            "message": message,
            "tool": tool_name,
        },
        ensure_ascii=False,
    )


def truncate_df(df: pd.DataFrame, max_rows: int = 50) -> pd.DataFrame:
    """Truncate a DataFrame to max_rows, adding a note if truncated."""
    if len(df) <= max_rows:
        return df
    return df.head(max_rows)
