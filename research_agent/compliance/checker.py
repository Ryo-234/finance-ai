"""合规检查器 —— 验证报告是否符合监管要求。"""

import re
import logging
from typing import List, Dict
from config.prompts.compliance import (
    DISCLAIMER_TEMPLATES,
    AI_MARKER,
    FORBIDDEN_PATTERNS,
    MANDATORY_CHECKLIST,
)

logger = logging.getLogger(__name__)


class ComplianceChecker:
    """金融报告合规检查器。

    检查项：
    1. 免责声明是否完整
    2. AI 标识是否在页首或页尾出现
    3. 数据来源是否标注
    4. 是否包含禁止用语（投资建议、夸大表述等）
    5. 是否包含敏感内容
    """

    def __init__(self):
        self.forbidden_patterns = [re.compile(p) for p in FORBIDDEN_PATTERNS]

    def check(self, content: str, sources: list = None, report_type: str = "default") -> Dict:
        """对报告内容执行全面合规检查。

        返回：
            {
                "passed": bool,
                "checks": [{"name": str, "passed": bool, "detail": str}],
                "violations": [str],
                "score": 0-100,
            }
        """
        checks = []
        violations = []

        # 1. 检查免责声明
        disclaimer_template = DISCLAIMER_TEMPLATES.get(report_type, DISCLAIMER_TEMPLATES["default"])
        disclaimer_key = disclaimer_template[:30]
        has_disclaimer = disclaimer_key in content
        checks.append({
            "name": "免责声明存在",
            "passed": has_disclaimer,
            "detail": "报告末尾包含完整的免责声明" if has_disclaimer else "缺少免责声明",
        })
        if not has_disclaimer:
            violations.append("报告缺少免责声明")

        # 2. 检查 AI 标识
        has_ai_marker = AI_MARKER in content
        checks.append({
            "name": "AI 标识存在",
            "passed": has_ai_marker,
            "detail": "包含 AI 生成内容标识" if has_ai_marker else "缺少 AI 标识",
        })
        if not has_ai_marker:
            violations.append("报告缺少 AI 生成内容标识")

        # 3. 检查来源标注
        has_source_annotation = bool(re.findall(r'\[\d+\]', content)) or (
            sources and len(sources) > 0
        )
        checks.append({
            "name": "来源标注完整性",
            "passed": has_source_annotation,
            "detail": "数据点标注了来源" if has_source_annotation else "缺少数据来源标注",
        })
        if not has_source_annotation:
            violations.append("报告缺少数据来源标注")

        # 4. 检查禁止用语
        forbidden_found = []
        for pattern in self.forbidden_patterns:
            matches = pattern.findall(content)
            if matches:
                forbidden_found.extend(matches)

        no_forbidden = len(forbidden_found) == 0
        checks.append({
            "name": "禁止用语检查",
            "passed": no_forbidden,
            "detail": "无禁止用语" if no_forbidden else f"发现禁止用语: {forbidden_found}",
        })
        if not no_forbidden:
            violations.append(f"报告包含禁止用语: {forbidden_found}")

        # 5. 检查投资建议
        investment_advice_patterns = [
            r"(建议|推荐).{0,5}(买入|卖出|持有|加仓|减仓)",
            r"目标价\s*\d+",
        ]
        has_advice = False
        for p in investment_advice_patterns:
            if re.search(p, content):
                has_advice = True
                break
        checks.append({
            "name": "投资建议检查",
            "passed": not has_advice,
            "detail": "不含投资建议" if not has_advice else "包含疑似投资建议",
        })
        if has_advice:
            violations.append("报告包含疑似投资建议（买卖方向+目标价）")

        # 计算得分
        passed_count = sum(1 for c in checks if c["passed"])
        score = int((passed_count / len(checks)) * 100)

        return {
            "passed": len(violations) == 0,
            "checks": checks,
            "violations": violations,
            "score": score,
        }

    def inject_compliance(self, content: str, report_type: str = "default") -> str:
        """在报告内容中注入合规声明。

        自动添加 AI 标识（页首）和免责声明（页尾）。
        """
        # 页首添加 AI 标识
        if AI_MARKER not in content:
            content = f"{AI_MARKER}\n\n{content}"

        # 页尾添加免责声明
        disclaimer = DISCLAIMER_TEMPLATES.get(report_type, DISCLAIMER_TEMPLATES["default"])
        if disclaimer[:30] not in content:
            content = f"{content}\n\n---\n\n{disclaimer}"

        return content
