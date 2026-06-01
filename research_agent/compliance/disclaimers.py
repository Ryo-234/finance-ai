"""声明管理器 —— 按报告类型管理免责声明模板。"""

from config.prompts.compliance import DISCLAIMER_TEMPLATES, AI_MARKER


class DisclaimerManager:
    """免责声明管理器。

    管理不同报告类型对应的免责声明模板，支持自定义和扩展。
    """

    def __init__(self):
        self._templates = dict(DISCLAIMER_TEMPLATES)
        self._custom_templates = {}

    def get(self, report_type: str = "default") -> str:
        """获取免责声明文本。"""
        if report_type in self._custom_templates:
            return self._custom_templates[report_type]
        return self._templates.get(report_type, self._templates["default"])

    def register(self, report_type: str, template: str):
        """注册自定义免责声明。"""
        self._custom_templates[report_type] = template

    def inject(self, content: str, report_type: str = "default") -> str:
        """向报告内容注入合规声明（AI 标识 + 免责声明）。

        参数：
            content: 原始报告 Markdown 内容
            report_type: 报告类型

        返回：
            注入后的完整内容
        """
        disclaimer = self.get(report_type)

        # 页首 AI 标识
        if AI_MARKER not in content:
            content = f"{AI_MARKER}\n\n{content}"

        # 页尾免责声明（检查前 50 字符避免重复）
        if disclaimer[:50] not in content:
            content = f"{content}\n\n---\n\n{disclaimer}"

        return content
