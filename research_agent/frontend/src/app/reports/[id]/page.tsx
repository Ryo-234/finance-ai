"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Spinner } from "@/components/Spinner";
import { EmptyState } from "@/components/EmptyState";
import { useAuth } from "@/hooks/useAuth";
import { ArrowLeft, FileText, Download, Share2, LogOut } from "lucide-react";

interface Report {
  id: string;
  title: string;
  report_type: string;
  topic: string;
  content: string;
  sources: Array<{ name?: string; url?: string; type?: string }>;
  status: string;
  compliance_status: string;
  token_used: number;
  created_at: string;
}

const TYPE_LABELS: Record<string, string> = {
  industry_research: "行业研究",
  company_deep: "公司深度",
  macro_brief: "宏观简报",
  strategy_daily: "策略日报",
};

async function downloadReport(reportId: string, format: "pdf" | "markdown") {
  const token = localStorage.getItem("auth_token");
  const res = await fetch(
    `http://localhost:8001/api/reports/${reportId}/export?format=${format}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  );
  if (!res.ok) {
    throw new Error("导出失败");
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  // 提取文件名（从 Content-Disposition 头）
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="([^"]+)"/);
  a.download = match ? match[1] : `report.${format === "pdf" ? "pdf" : "md"}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const { user, logout } = useAuth();
  const router = useRouter();

  const planName =
    user?.plan_type === "pro"
      ? "专业版"
      : user?.plan_type === "enterprise"
        ? "企业版"
        : "免费版";

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    fetch(`http://localhost:8001/api/reports/${id}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => res.json())
      .then((data) => setReport(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Spinner className="w-8 h-8" style={{ color: '#d97706' }} />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <EmptyState
          icon={<FileText className="w-12 h-12" />}
          title="报告不存在"
          description="该报告可能已被删除或您没有访问权限"
          action={
            <Link
              href="/reports"
              className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              返回报告中心
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        {/* 主行：品牌 + 站点导航 + 用户信息（与其他页面保持一致） */}
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/chat" className="text-xl font-bold" style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}>
              金融投研 AI
            </Link>
            <div className="flex gap-5 text-sm">
              <Link href="/chat" className="text-gray-500 hover:text-gray-900 transition-colors">对话研究</Link>
              <Link href="/dashboard" className="text-gray-500 hover:text-gray-900 transition-colors">仪表板</Link>
              <Link href="/reports" className="text-amber-700 font-medium">报告中心</Link>
            </div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full text-xs">{planName}</span>
            <span className="text-gray-600">{user?.display_name || user?.email}</span>
            <button
              onClick={handleLogout}
              className="text-gray-400 hover:text-gray-600 transition-colors flex items-center gap-1"
              title="退出登录"
            >
              <LogOut className="w-3.5 h-3.5" />
              退出
            </button>
          </div>
        </div>

        {/* 报告行：面包屑 + 标题 + 元信息 + 操作 */}
        <div className="border-t border-gray-50 bg-gradient-to-b from-gray-50/30 to-white">
          <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-4">
            {/* 面包屑 + 标题 */}
            <nav className="flex items-center gap-2 text-sm text-gray-400 min-w-0 flex-1">
              <Link href="/reports" className="hover:text-gray-600 transition-colors whitespace-nowrap">
                报告中心
              </Link>
              <span className="text-gray-300">/</span>
              <span className="text-gray-700 font-medium truncate" title={report.title}>
                {report.title}
              </span>
            </nav>

            {/* 分隔 */}
            <div className="w-px h-5 bg-gray-200 shrink-0" />

            {/* 元信息：类型 + 合规 */}
            <div className="flex items-center gap-3 shrink-0">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-50 text-amber-700 rounded-md text-xs font-medium">
                <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
                {TYPE_LABELS[report.report_type] || report.report_type}
              </span>
              <span
                className={
                  report.compliance_status === "passed"
                    ? "inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600"
                    : "inline-flex items-center gap-1.5 text-xs font-medium text-red-500"
                }
              >
                <span
                  className={
                    report.compliance_status === "passed"
                      ? "w-1.5 h-1.5 bg-emerald-500 rounded-full"
                      : "w-1.5 h-1.5 bg-red-500 rounded-full"
                  }
                />
                {report.compliance_status === "passed" ? "合规通过" : "合规未通过"}
              </span>
            </div>

            {/* 分隔 */}
            <div className="w-px h-5 bg-gray-200 shrink-0" />

            {/* 操作按钮 */}
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => downloadReport(report.id, "pdf").catch(() => alert("PDF 导出失败"))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-amber-600 text-white text-xs font-medium hover:bg-amber-700 transition-colors"
                title="导出 PDF 文件"
              >
                <Download className="w-3.5 h-3.5" />
                导出 PDF
              </button>
              <button
                onClick={() => downloadReport(report.id, "markdown").catch(() => alert("Markdown 导出失败"))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 text-gray-600 text-xs font-medium hover:border-amber-300 hover:text-amber-700 transition-colors"
                title="导出 Markdown 源文件"
              >
                <Download className="w-3.5 h-3.5" />
                .md
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <div className="bg-white rounded-2xl shadow-sm p-8">
          <div className="mb-6 pb-6 border-b border-gray-100">
            <h1 className="text-2xl font-bold text-gray-900 mb-2">{report.title}</h1>
            <p className="text-sm text-gray-500">研究课题：{report.topic}</p>
            <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
              <span>{report.token_used.toLocaleString()} Token</span>
              <span>{new Date(report.created_at).toLocaleString("zh-CN")}</span>
            </div>
          </div>

          <div className="markdown-content max-w-none">
            {renderMarkdown(report.content)}
          </div>

          {report.sources && report.sources.length > 0 && (
            <div className="mt-8 pt-6 border-t border-gray-100">
              <h3 className="text-sm font-medium text-gray-500 mb-3">数据来源</h3>
              <ul className="space-y-1">
                {report.sources.map((s, i) => (
                  <li key={i} className="text-xs text-gray-400">
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noopener noreferrer" className="hover:text-amber-600 underline">
                        [{i + 1}] {s.name || s.url}
                      </a>
                    ) : (
                      `[${i + 1}] ${s.name || "未知来源"}`
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

// Markdown 渲染（支持标题/列表/表格/引用/代码/加粗/链接/分割线）
function renderMarkdown(content: string): React.ReactNode[] {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  // 处理行内格式：加粗、斜体、代码、链接
  const inline = (text: string): React.ReactNode => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let partKey = 0;
    const regex = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\))/g;
    let lastIndex = 0;
    let match;
    while ((match = regex.exec(text)) !== null) {
      if (match.index > lastIndex) {
        parts.push(text.slice(lastIndex, match.index));
      }
      if (match[2]) {
        parts.push(<strong key={partKey++} className="font-semibold text-gray-900">{match[2]}</strong>);
      } else if (match[3]) {
        parts.push(<em key={partKey++} className="italic">{match[3]}</em>);
      } else if (match[4]) {
        parts.push(<code key={partKey++} className="px-1.5 py-0.5 bg-gray-100 text-pink-600 rounded text-sm font-mono">{match[4]}</code>);
      } else if (match[5] && match[6]) {
        parts.push(<a key={partKey++} href={match[6]} target="_blank" rel="noopener noreferrer" className="text-amber-600 hover:underline">{match[5]}</a>);
      }
      lastIndex = regex.lastIndex;
    }
    if (lastIndex < text.length) {
      parts.push(text.slice(lastIndex));
    }
    return parts.length > 0 ? parts : text;
  };

  while (i < lines.length) {
    const line = lines[i];

    // 空行
    if (line.trim() === "") {
      i++;
      continue;
    }

    // 分割线
    if (/^---+$/.test(line.trim())) {
      elements.push(<hr key={key++} className="my-6 border-gray-200" />);
      i++;
      continue;
    }

    // 标题
    if (line.startsWith("# ")) {
      elements.push(<h1 key={key++} className="text-2xl font-bold mt-8 mb-4 text-gray-900 pb-3 border-b border-gray-100">{inline(line.slice(2))}</h1>);
      i++;
      continue;
    }
    if (line.startsWith("## ")) {
      elements.push(<h2 key={key++} className="text-xl font-semibold mt-6 mb-3 text-gray-800">{inline(line.slice(3))}</h2>);
      i++;
      continue;
    }
    if (line.startsWith("### ")) {
      elements.push(<h3 key={key++} className="text-lg font-medium mt-4 mb-2 text-gray-700">{inline(line.slice(4))}</h3>);
      i++;
      continue;
    }

    // 引用块
    if (line.startsWith("> ")) {
      elements.push(<blockquote key={key++} className="border-l-4 border-amber-300 pl-4 py-1 my-2 text-gray-500 italic bg-amber-50/50">{inline(line.slice(2))}</blockquote>);
      i++;
      continue;
    }

    // 表格（| col | col |）
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      // 跳过对齐行 | --- | --- |
      const dataLines = tableLines.filter(l => !/^\|[\s-:|]+\|$/.test(l.trim()));
      if (dataLines.length > 0) {
        const parseRow = (l: string) => l.trim().slice(1, -1).split("|").map(c => c.trim());
        const headers = parseRow(dataLines[0]);
        const rows = dataLines.slice(1).map(parseRow);
        elements.push(
          <div key={key++} className="my-4 overflow-x-auto">
            <table className="w-full text-sm border border-gray-200 rounded-lg overflow-hidden">
              <thead className="bg-amber-50">
                <tr>
                  {headers.map((h, j) => (
                    <th key={j} className="px-4 py-2 text-left font-medium text-gray-700 border-b border-gray-200">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, j) => (
                  <tr key={j} className="hover:bg-gray-50">
                    {row.map((c, k) => (
                      <td key={k} className="px-4 py-2 border-b border-gray-100 text-gray-700">{inline(c)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      continue;
    }

    // 无序列表
    if (line.startsWith("- ") || line.startsWith("* ")) {
      const items: string[] = [];
      while (i < lines.length && (lines[i].startsWith("- ") || lines[i].startsWith("* "))) {
        items.push(lines[i].slice(2));
        i++;
      }
      elements.push(
        <ul key={key++} className="list-disc list-inside space-y-1 my-2 text-gray-700">
          {items.map((item, j) => <li key={j}>{inline(item)}</li>)}
        </ul>
      );
      continue;
    }

    // 有序列表
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      elements.push(
        <ol key={key++} className="list-decimal list-inside space-y-1 my-2 text-gray-700">
          {items.map((item, j) => <li key={j}>{inline(item)}</li>)}
        </ol>
      );
      continue;
    }

    // 普通段落
    elements.push(<p key={key++} className="text-gray-700 leading-relaxed mb-2">{inline(line)}</p>);
    i++;
  }

  return elements;
}
