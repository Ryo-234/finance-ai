"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

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

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);

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
        <div className="animate-spin h-8 w-8 border-2 border-amber-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <p className="text-gray-400 mb-4">报告不存在</p>
          <Link href="/reports" className="text-amber-600 hover:underline">返回报告列表</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="text-xl font-bold" style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}>
              金融投研 AI
            </Link>
            <span className="text-gray-300">/</span>
            <Link href="/reports" className="text-sm text-gray-500 hover:text-gray-900">报告中心</Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-700 truncate max-w-xs">{report.title}</span>
          </div>
          <div className="flex items-center gap-3 text-xs">
            <span className="px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full">
              {TYPE_LABELS[report.report_type] || report.report_type}
            </span>
            <span className={report.compliance_status === "passed" ? "text-green-600" : "text-red-500"}>
              {report.compliance_status === "passed" ? "合规通过" : "合规未通过"}
            </span>
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto px-6 py-8">
        <div className="bg-white rounded-2xl shadow-sm p-8">
          <div className="mb-6 pb-6 border-b border-gray-100">
            <h1 className="text-2xl font-bold text-gray-900 mb-2">{report.title}</h1>
            <p className="text-sm text-gray-500">研究课题：{report.topic}</p>
            <div className="flex items-center gap-4 mt-3 text-xs text-gray-400">
              <span>{report.token_used.toLocaleString()} Token</span>
              <span>{new Date(report.created_at).toLocaleString("zh-CN")}</span>
            </div>
          </div>

          <div className="prose prose-gray max-w-none">
            {report.content.split("\n").map((line, i) => {
              if (line.startsWith("# ")) {
                return <h1 key={i} className="text-2xl font-bold mt-8 mb-4 text-gray-900">{line.slice(2)}</h1>;
              }
              if (line.startsWith("## ")) {
                return <h2 key={i} className="text-xl font-semibold mt-6 mb-3 text-gray-800">{line.slice(3)}</h2>;
              }
              if (line.startsWith("### ")) {
                return <h3 key={i} className="text-lg font-medium mt-4 mb-2 text-gray-700">{line.slice(4)}</h3>;
              }
              if (line.startsWith("- ")) {
                return <li key={i} className="ml-4 text-gray-700">{line.slice(2)}</li>;
              }
              if (line.startsWith("> ")) {
                return <blockquote key={i} className="border-l-4 border-amber-300 pl-4 py-1 my-2 text-gray-500 italic">{line.slice(2)}</blockquote>;
              }
              if (line.trim() === "") {
                return <br key={i} />;
              }
              return <p key={i} className="text-gray-700 leading-relaxed mb-2">{line}</p>;
            })}
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
