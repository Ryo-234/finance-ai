"""报告导出服务 —— 支持 Markdown 和 PDF 两种格式。"""

import io
import re
import logging
from datetime import datetime
from typing import Tuple

logger = logging.getLogger(__name__)


class ReportExporter:
    """报告导出器。

    支持格式：
    - markdown: 直接返回原始 Markdown 文本
    - pdf: 用 reportlab 将 Markdown 渲染为 PDF
    """

    def export(self, content: str, title: str, format: str = "markdown") -> Tuple[bytes, str, str]:
        """导出报告。

        参数：
            content: 报告 Markdown 内容
            title: 报告标题
            format: 格式（markdown / pdf）

        返回：
            (文件二进制, MIME 类型, 文件名)
        """
        if format == "markdown" or format == "md":
            return self._export_markdown(content, title)
        elif format == "pdf":
            return self._export_pdf(content, title)
        else:
            raise ValueError(f"不支持的导出格式: {format}")

    def _export_markdown(self, content: str, title: str) -> Tuple[bytes, str, str]:
        """导出为 Markdown 文件。"""
        # 添加 YAML 头
        header = f"""---
title: {title}
exported_at: {datetime.utcnow().isoformat()}Z
generator: 金融投研 AI v1.0
---

"""
        markdown_bytes = (header + content).encode("utf-8")
        safe_title = re.sub(r'[^\w\-_]', '_', title)[:50]
        return markdown_bytes, "text/markdown", f"{safe_title}.md"

    def _export_pdf(self, content: str, title: str) -> Tuple[bytes, str, str]:
        """导出为 PDF（用 reportlab）。"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib.colors import HexColor
            from reportlab.lib.enums import TA_LEFT, TA_CENTER
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
            )

            # 注册中文字体
            try:
                pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
                chinese_font = "STSong-Light"
            except Exception:
                chinese_font = "Helvetica"

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                leftMargin=2 * cm,
                rightMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm,
                title=title,
                author="金融投研 AI",
            )

            # 样式定义
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                "TitleCN", parent=styles["Title"],
                fontName=chinese_font, fontSize=22, leading=28,
                textColor=HexColor("#92400e"), alignment=TA_CENTER, spaceAfter=20,
            )
            h1_style = ParagraphStyle(
                "H1CN", parent=styles["Heading1"],
                fontName=chinese_font, fontSize=18, leading=24,
                textColor=HexColor("#92400e"), spaceBefore=16, spaceAfter=12,
                borderWidth=0, borderColor=HexColor("#fcd34d"),
                borderPadding=4,
            )
            h2_style = ParagraphStyle(
                "H2CN", parent=styles["Heading2"],
                fontName=chinese_font, fontSize=14, leading=20,
                textColor=HexColor("#b45309"), spaceBefore=12, spaceAfter=8,
            )
            h3_style = ParagraphStyle(
                "H3CN", parent=styles["Heading3"],
                fontName=chinese_font, fontSize=12, leading=18,
                textColor=HexColor("#78350f"), spaceBefore=8, spaceAfter=6,
            )
            body_style = ParagraphStyle(
                "BodyCN", parent=styles["Normal"],
                fontName=chinese_font, fontSize=10, leading=16,
                textColor=HexColor("#374151"), spaceAfter=6,
                alignment=TA_LEFT,
            )
            quote_style = ParagraphStyle(
                "QuoteCN", parent=body_style,
                leftIndent=20, fontSize=10,
                textColor=HexColor("#6b7280"), fontName=chinese_font,
                borderColor=HexColor("#fcd34d"), borderWidth=0, borderLeftWidth=3,
                borderPadding=6,
            )

            story = []

            # 处理 Markdown 行
            lines = content.split("\n")
            i = 0
            in_table = False
            table_rows: list = []

            def clean_text(text: str) -> str:
                """清理 Markdown 标记为 reportlab 标签。"""
                text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
                text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
                text = re.sub(r'`([^`]+)`', r'<font face="Courier">\1</font>', text)
                text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                # 恢复我们刚加粗的标签（仅恢复 <b> 和 <i>，其他保持转义）
                text = text.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
                text = text.replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")
                return text

            def flush_table():
                """渲染累积的表格。"""
                nonlocal table_rows
                if not table_rows:
                    return
                data = [[clean_text(c) for c in row] for row in table_rows]
                t = Table(data, colWidths=[(doc.width / len(table_rows[0]))] * len(table_rows[0]))
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#fef3c7")),
                    ("FONTNAME", (0, 0), (-1, -1), chinese_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#78350f")),
                    ("TEXTCOLOR", (0, 1), (-1, -1), HexColor("#374151")),
                    ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(t)
                story.append(Spacer(1, 8))
                table_rows = []

            # 文档标题
            story.append(Paragraph(clean_text(title), title_style))
            story.append(Paragraph(
                f"<font size=9 color='#6b7280'>导出时间：{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</font>",
                body_style
            ))
            story.append(Spacer(1, 12))

            while i < len(lines):
                line = lines[i]

                # 表格
                if line.strip().startswith("|") and line.strip().endswith("|"):
                    cells = [c.strip() for c in line.strip()[1:-1].split("|")]
                    # 跳过分隔行 |---|---|
                    if not all(re.match(r'^[-:]+$', c) for c in cells):
                        table_rows.append(cells)
                    in_table = True
                    i += 1
                    continue
                elif in_table:
                    flush_table()
                    in_table = False

                if line.startswith("# "):
                    story.append(Paragraph(clean_text(line[2:]), h1_style))
                elif line.startswith("## "):
                    story.append(Paragraph(clean_text(line[3:]), h2_style))
                elif line.startswith("### "):
                    story.append(Paragraph(clean_text(line[4:]), h3_style))
                elif line.startswith("> "):
                    story.append(Paragraph(clean_text(line[2:]), quote_style))
                elif line.startswith("- ") or line.startswith("* "):
                    items = []
                    while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("* ")):
                        items.append(lines[i][2:])
                        i += 1
                    for item in items:
                        story.append(Paragraph("• " + clean_text(item), body_style))
                    continue
                elif re.match(r'^\d+\.\s', line):
                    items = []
                    while i < len(lines) and re.match(r'^\d+\.\s', lines[i]):
                        items.append(re.sub(r'^\d+\.\s', '', lines[i]))
                        i += 1
                    for idx, item in enumerate(items, 1):
                        story.append(Paragraph(f"{idx}. {clean_text(item)}", body_style))
                    continue
                elif line.strip() == "":
                    story.append(Spacer(1, 4))
                else:
                    story.append(Paragraph(clean_text(line), body_style))
                i += 1

            flush_table()

            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            safe_title = re.sub(r'[^\w\-_]', '_', title)[:50]
            return pdf_bytes, "application/pdf", f"{safe_title}.pdf"

        except ImportError as e:
            logger.error(f"reportlab 导入失败: {e}")
            raise RuntimeError("PDF 导出功能需要安装 reportlab")


# 全局单例
_exporter: ReportExporter | None = None


def export_report(content: str, title: str, format: str = "markdown") -> Tuple[bytes, str, str]:
    """便捷函数：导出报告。"""
    global _exporter
    if _exporter is None:
        _exporter = ReportExporter()
    return _exporter.export(content, title, format)
