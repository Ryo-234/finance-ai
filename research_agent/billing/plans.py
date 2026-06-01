"""订阅方案定义。"""

SUBSCRIPTION_PLANS = {
    "free": {
        "name": "免费版",
        "monthly_price": 0,
        "monthly_reports": 3,
        "max_tokens_per_month": 50000,
        "data_sources": ["eastmoney_free"],
        "report_types": ["quick_analysis"],
        "export_formats": ["markdown"],
        "support": "none",
        "features": [],
    },
    "pro": {
        "name": "专业版",
        "monthly_price": 299,
        "monthly_reports": -1,  # 无限制
        "max_tokens_per_month": 500000,
        "data_sources": ["eastmoney_full", "sina_finance"],
        "report_types": ["all"],
        "export_formats": ["markdown", "pdf"],
        "support": "email_48h",
        "features": ["unlimited_reports", "advanced_templates", "data_export"],
    },
    "enterprise": {
        "name": "企业版",
        "monthly_price": 2999,
        "seats_included": 5,
        "extra_seat_price": 299,
        "monthly_reports": -1,
        "max_tokens_per_month": 3000000,
        "data_sources": ["eastmoney_full", "sina_finance", "cninfo"],
        "report_types": ["all"],
        "export_formats": ["markdown", "pdf", "word"],
        "support": "dedicated_wechat",
        "features": ["unlimited_reports", "advanced_templates", "data_export", "api_access", "custom_template"],
    },
}


def get_plan(plan_type: str) -> dict:
    """获取方案定义。"""
    return SUBSCRIPTION_PLANS.get(plan_type, SUBSCRIPTION_PLANS["free"])


def get_plan_limits(plan_type: str) -> dict:
    """获取方案的用量限制。"""
    plan = get_plan(plan_type)
    return {
        "monthly_reports": plan["monthly_reports"],
        "max_tokens_per_month": plan["max_tokens_per_month"],
        "data_sources": plan["data_sources"],
    }
