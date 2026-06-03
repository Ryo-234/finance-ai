"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/core/api";
import { Spinner } from "@/components/Spinner";
import { EmptyState } from "@/components/EmptyState";
import { ArrowLeft, Clock, CheckCircle2, XCircle, Loader2, RefreshCw, FileText } from "lucide-react";

interface Task {
  id: string;
  topic: string;
  report_type: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  current_stage: string;
  result_report_id: string | null;
  error_message: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

const STATUS_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: "等待中", color: "text-amber-700", bg: "bg-amber-50" },
  running: { label: "生成中", color: "text-blue-700", bg: "bg-blue-50" },
  completed: { label: "已完成", color: "text-green-700", bg: "bg-green-50" },
  failed: { label: "失败", color: "text-red-700", bg: "bg-red-50" },
  cancelled: { label: "已取消", color: "text-gray-500", bg: "bg-gray-50" },
};

const TYPE_LABELS: Record<string, string> = {
  industry_research: "行业研究",
  company_deep: "公司深度",
  macro_brief: "宏观简报",
  strategy_daily: "策略日报",
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem("auth_token");
    if (!stored) {
      router.push("/login");
      return;
    }
    loadTasks(stored);
    // 轮询：每 3 秒刷新（任务列表变化频繁）
    const timer = setInterval(() => loadTasks(stored), 3000);
    return () => clearInterval(timer);
  }, [router]);

  const loadTasks = async (token: string) => {
    try {
      const data: any = await api.listTasks(20, undefined, token);
      setTasks(data.tasks || []);
    } catch (err) {
      console.error("加载任务列表失败:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (taskId: string) => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    try {
      await api.retryTask(taskId, token);
      loadTasks(token);
    } catch (err) {
      console.error("重试失败:", err);
    }
  };

  const handleCancel = async (taskId: string) => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    try {
      await api.cancelTask(taskId, token);
      loadTasks(token);
    } catch (err) {
      console.error("取消失败:", err);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航 */}
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/chat" className="text-xl font-bold" style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}>
              金融投研 AI
            </Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-700">任务中心</span>
          </div>
          <Link
            href="/dashboard"
            className="text-sm text-gray-500 hover:text-amber-600 transition-colors flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" />
            返回仪表板
          </Link>
        </div>
      </nav>

      <main className="max-w-5xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2" style={{ fontFamily: "Crimson Pro, serif" }}>
          任务中心
        </h1>
        <p className="text-sm text-gray-500 mb-6">
          后台异步生成报告，刷新或切走都不影响
        </p>

        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner className="w-8 h-8" style={{ color: '#d97706' }} />
          </div>
        ) : tasks.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-100">
            <EmptyState
              icon={<Clock className="w-12 h-12" />}
              title="暂无任务"
              description="去对话研究提交课题，任务会出现在这里"
              action={
                <Link
                  href="/chat"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 transition-colors"
                >
                  提交任务
                </Link>
              }
            />
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => {
              const status = STATUS_LABELS[task.status] || STATUS_LABELS.pending;
              return (
                <Link
                  key={task.id}
                  href={`/tasks/${task.id}`}
                  className="block bg-white rounded-xl border border-gray-100 p-5 hover:border-amber-200 hover:shadow-sm transition-all"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-gray-900 line-clamp-1 mb-1">
                        {task.topic}
                      </h3>
                      <div className="flex items-center gap-2 text-xs text-gray-500">
                        <span className="px-2 py-0.5 bg-amber-50 text-amber-700 rounded">
                          {TYPE_LABELS[task.report_type] || task.report_type}
                        </span>
                        <span>·</span>
                        <span className={status.color}>{status.label}</span>
                        {task.current_stage && (
                          <>
                            <span>·</span>
                            <span className="text-gray-400">{task.current_stage}</span>
                          </>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {task.status === "running" && (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                          <button
                            onClick={(e) => {
                              e.preventDefault()
                              e.stopPropagation()
                              if (confirm(`确定停止任务"${task.topic}"？`)) {
                                handleCancel(task.id)
                              }
                            }}
                            className="px-2 py-1 text-xs text-red-600 border border-red-200 rounded hover:bg-red-50 transition-colors"
                            title="停止生成"
                          >
                            停止
                          </button>
                        </>
                      )}
                      {task.status === "completed" && (
                        <CheckCircle2 className="w-5 h-5 text-green-600" />
                      )}
                      {task.status === "failed" && (
                        <XCircle className="w-5 h-5 text-red-600" />
                      )}
                      {task.status === "cancelled" && (
                        <XCircle className="w-5 h-5 text-gray-400" />
                      )}
                    </div>
                  </div>

                  {/* 进度条 */}
                  {task.status === "running" || task.status === "pending" ? (
                    <div className="mt-3">
                      <div className="flex justify-between text-xs text-gray-500 mb-1">
                        <span>进度</span>
                        <span>{task.progress}%</span>
                      </div>
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all duration-500"
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                    </div>
                  ) : task.status === "completed" && task.result_report_id ? (
                    <div className="mt-3 flex items-center gap-2 text-xs text-green-600">
                      <FileText className="w-4 h-4" />
                      报告已生成，点击查看
                    </div>
                  ) : task.status === "failed" ? (
                    <div className="mt-3 flex items-center justify-between">
                      <div className="text-xs text-red-600 line-clamp-1 flex-1">
                        {task.error_message}
                      </div>
                      <button
                        onClick={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          handleRetry(task.id)
                        }}
                        className="ml-3 px-3 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-700 flex items-center gap-1"
                      >
                        <RefreshCw className="w-3 h-3" />
                        重试
                      </button>
                    </div>
                  ) : null}
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
