"use client";

import Link from "next/link";

interface ReportCardProps {
  id: string;
  title: string;
  report_type: string;
  status: string;
  compliance_status: string;
  created_at: string;
  token_used: number;
}

const TYPE_LABELS: Record<string, string> = {
  industry_research: "行业研究",
  company_deep: "公司深度",
  macro_brief: "宏观简报",
  strategy_daily: "策略日报",
};

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-green-100 text-green-700",
  draft: "bg-gray-100 text-gray-600",
  failed: "bg-red-100 text-red-700",
};

const COMPLIANCE_LABELS: Record<string, string> = {
  passed: "合规通过",
  failed: "合规未通过",
  pending: "合规待检",
};

export default function ReportCard({ id, title, report_type, status, compliance_status, created_at, token_used }: ReportCardProps) {
  return (
    <Link href={`/reports/${id}`}>
      <div className="bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md transition-shadow cursor-pointer">
        <div className="flex items-start justify-between mb-3">
          <h3 className="font-semibold text-gray-900 line-clamp-2 flex-1">{title}</h3>
          <span className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[status] || "bg-gray-100"}`}>
            {status === "completed" ? "已完成" : status === "draft" ? "草稿" : "失败"}
          </span>
        </div>

        <div className="flex items-center gap-3 text-xs text-gray-500 mb-3">
          <span className="bg-amber-50 text-amber-700 px-2 py-0.5 rounded">
            {TYPE_LABELS[report_type] || report_type}
          </span>
          <span>{COMPLIANCE_LABELS[compliance_status] || compliance_status}</span>
          <span>{token_used.toLocaleString()} Token</span>
        </div>

        <div className="text-xs text-gray-400">
          {new Date(created_at).toLocaleDateString("zh-CN", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>
    </Link>
  );
}
