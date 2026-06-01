"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
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

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    fetch("http://localhost:8001/api/reports/?limit=50", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => res.json())
      .then((data) => setReports(data.reports || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/dashboard" className="text-xl font-bold" style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}>
              金融投研 AI
            </Link>
            <div className="flex gap-4 text-sm">
              <Link href="/chat" className="text-gray-500 hover:text-gray-900">对话研究</Link>
              <Link href="/dashboard" className="text-gray-500 hover:text-gray-900">仪表板</Link>
              <Link href="/reports" className="text-amber-700 font-medium">报告中心</Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6" style={{ fontFamily: "Crimson Pro, serif" }}>
          报告中心
        </h1>

        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin h-8 w-8 border-2 border-amber-600 border-t-transparent rounded-full" />
          </div>
        ) : reports.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-100 p-12 text-center">
            <p className="text-gray-400 mb-3">还没有报告</p>
            <Link href="/chat" className="inline-block px-4 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700">
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
      </main>
    </div>
  );
}
