"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/hooks/useAuth";
import ReportCard from "@/components/ReportCard";

interface Report {
  id: string;
  title: string;
  report_type: string;
  status: string;
  compliance_status: string;
  token_used: number;
  created_at: string;
}

interface UsageInfo {
  reports_this_month: number;
  tokens_this_month: number;
  report_limit: number;
  token_limit: number;
  daily_stats: Array<{ date: string; reports: number; tokens: number }>;
}

export default function DashboardPage() {
  const { user, token, loading: authLoading } = useAuth();
  const [reports, setReports] = useState<Report[]>([]);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && !user) {
      router.push("/login");
      return;
    }
    if (token) {
      loadData();
    }
  }, [user, authLoading, token]);

  const loadData = async () => {
    try {
      const [reportsRes, usageRes] = await Promise.all([
        fetch("http://localhost:8001/api/reports/?limit=5", {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch("http://localhost:8001/api/billing/usage", {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      if (reportsRes.ok) {
        const data = await reportsRes.json();
        setReports(data.reports || []);
      }
      if (usageRes.ok) {
        const data = await usageRes.json();
        setUsage(data);
      }
    } catch (err) {
      console.error("加载数据失败:", err);
    } finally {
      setLoading(false);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin h-8 w-8 border-2 border-amber-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  const planName = user?.plan_type === "pro" ? "专业版" : user?.plan_type === "enterprise" ? "企业版" : "免费版";

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 导航栏 */}
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/dashboard" className="text-xl font-bold" style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}>
              金融投研 AI
            </Link>
            <div className="flex gap-4 text-sm">
              <Link href="/dashboard" className="text-amber-700 font-medium">仪表板</Link>
              <Link href="/chat" className="text-gray-500 hover:text-gray-900">对话研究</Link>
              <Link href="/reports" className="text-gray-500 hover:text-gray-900">报告中心</Link>
            </div>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="px-2 py-0.5 bg-amber-50 text-amber-700 rounded-full text-xs">{planName}</span>
            <span className="text-gray-600">{user?.display_name || user?.email}</span>
            <button
              onClick={() => { localStorage.removeItem("auth_token"); router.push("/login"); }}
              className="text-gray-400 hover:text-gray-600"
            >
              退出
            </button>
          </div>
        </div>
      </nav>

      {/* 主内容 */}
      <main className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6" style={{ fontFamily: "Crimson Pro, serif" }}>
          研究仪表板
        </h1>

        {/* 用量卡片 */}
        {usage && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <p className="text-sm text-gray-500 mb-1">本月报告</p>
              <p className="text-2xl font-bold text-gray-900">
                {usage.reports_this_month}
                <span className="text-sm text-gray-400 font-normal">
                  {usage.report_limit > 0 ? ` / ${usage.report_limit}` : " / 无限"}
                </span>
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <p className="text-sm text-gray-500 mb-1">本月 Token</p>
              <p className="text-2xl font-bold text-gray-900">
                {(usage.tokens_this_month / 1000).toFixed(1)}K
                <span className="text-sm text-gray-400 font-normal">
                  {usage.token_limit > 0 ? ` / ${(usage.token_limit / 1000).toFixed(0)}K` : " / 无限"}
                </span>
              </p>
            </div>
            <div className="bg-white rounded-xl border border-gray-100 p-5">
              <p className="text-sm text-gray-500 mb-1">订阅方案</p>
              <p className="text-2xl font-bold text-amber-600">{planName}</p>
            </div>
          </div>
        )}

        {/* 快捷入口 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {[
            { type: "industry_research", label: "行业研究", icon: "🏭" },
            { type: "company_deep", label: "公司深度", icon: "🏢" },
            { type: "macro_brief", label: "宏观简报", icon: "📊" },
            { type: "strategy_daily", label: "策略日报", icon: "📈" },
          ].map((item) => (
            <Link
              key={item.type}
              href={`/chat?type=${item.type}`}
              className="bg-white rounded-xl border border-gray-100 p-4 text-center hover:border-amber-200 hover:shadow-sm transition-all"
            >
              <div className="text-2xl mb-2">{item.icon}</div>
              <div className="text-sm font-medium text-gray-700">{item.label}</div>
            </Link>
          ))}
        </div>

        {/* 最近报告 */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">最近报告</h2>
            <Link href="/reports" className="text-sm text-amber-600 hover:underline">
              查看全部
            </Link>
          </div>
          {reports.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
              <p className="text-gray-400 mb-3">还没有报告</p>
              <Link
                href="/chat"
                className="inline-block px-4 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700"
              >
                开始研究
              </Link>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {reports.map((r) => (
                <ReportCard key={r.id} {...r} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
