"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/core/api";
import { Spinner } from "@/components/Spinner";
import { ArrowLeft, Loader2, CheckCircle2, XCircle, RefreshCw, ArrowRight, Clock } from "lucide-react";

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

const TYPE_LABELS: Record<string, string> = {
  industry_research: "行业研究",
  company_deep: "公司深度",
  macro_brief: "宏观简报",
  strategy_daily: "策略日报",
};

const STAGE_LABELS: Record<string, string> = {
  planner: "分析意图和规划任务",
  finance_search: "从金融数据源获取数据",
  finance_knowledge: "按报告模板组织数据",
  report_synthesizer: "生成报告章节",
  cached: "缓存命中，直接返回",
};

export default function TaskDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: taskId } = use(params);
  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const stored = localStorage.getItem("auth_token");
    if (!stored) {
      router.push("/login");
      return;
    }
    loadTask(stored);
    // 轮询：2 秒一次（详情页需要更实时）
    const timer = setInterval(() => loadTask(stored), 2000);
    return () => clearInterval(timer);
  }, [taskId, router]);

  // 完成后自动跳报告
  useEffect(() => {
    if (task?.status === "completed" && task.result_report_id) {
      const timer = setTimeout(() => {
        router.push(`/reports/${task.result_report_id}`);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [task?.status, task?.result_report_id, router]);

  const loadTask = async (token: string) => {
    try {
      const data: any = await api.getTask(taskId, token);
      setTask(data);
    } catch (err: any) {
      console.error("加载任务失败:", err);
      // 任务不存在/无权访问
      if (err.message?.includes("404") || err.message?.includes("403")) {
        router.push("/tasks");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    try {
      const newTask: any = await api.retryTask(taskId, token);
      router.push(`/tasks/${newTask.id}`);
    } catch (err) {
      console.error("重试失败:", err);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Spinner className="w-8 h-8" style={{ color: '#d97706' }} />
      </div>
    );
  }

  if (!task) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-500">任务不存在</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* 顶部导航 */}
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/chat" className="text-xl font-bold" style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}>
              金融投研 AI
            </Link>
            <span className="text-gray-300">/</span>
            <Link href="/tasks" className="text-sm text-gray-500 hover:text-amber-600">任务中心</Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-700">{taskId.slice(0, 8)}</span>
          </div>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-8">
        {/* 状态卡片 */}
        <div className="bg-white rounded-2xl shadow-sm p-8 mb-6">
          {/* 标题和状态 */}
          <div className="flex items-start justify-between mb-6">
            <div className="flex-1 min-w-0">
              <h1 className="text-2xl font-bold text-gray-900 mb-2">{task.topic}</h1>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span className="px-2 py-0.5 bg-amber-50 text-amber-700 rounded">
                  {TYPE_LABELS[task.report_type] || task.report_type}
                </span>
                <span>·</span>
                <span>{new Date(task.created_at).toLocaleString("zh-CN")}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 ml-4">
              {task.status === "running" && (
                <>
                  <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
                  <button
                    onClick={async () => {
                      const token = localStorage.getItem("auth_token");
                      if (!token) return;
                      if (!confirm(`确定停止任务"${task.topic}"？\n当前进度 ${task.progress}%`)) return;
                      try {
                        await api.cancelTask(task.id, token);
                        loadTask(token);  // 立即刷新
                      } catch (err) {
                        alert("停止失败：" + (err as any).message);
                      }
                    }}
                    className="px-3 py-1.5 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors flex items-center gap-1"
                    title="停止生成"
                  >
                    停止生成
                  </button>
                </>
              )}
              {task.status === "completed" && (
                <CheckCircle2 className="w-8 h-8 text-green-600" />
              )}
              {task.status === "failed" && (
                <XCircle className="w-8 h-8 text-red-600" />
              )}
              {task.status === "pending" && (
                <Clock className="w-8 h-8 text-amber-500" />
              )}
              {task.status === "cancelled" && (
                <XCircle className="w-8 h-8 text-gray-400" />
              )}
            </div>
          </div>

          {/* 进度条 */}
          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span className="font-medium text-gray-700">
                {task.status === "pending" && "等待开始..."}
                {task.status === "running" && (STAGE_LABELS[task.current_stage] || "正在生成报告...")}
                {task.status === "completed" && "报告已生成"}
                {task.status === "failed" && "任务失败"}
                {task.status === "cancelled" && "已取消"}
              </span>
              <span className="font-mono text-amber-600 font-bold">{task.progress}%</span>
            </div>
            <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-700 ${
                  task.status === "failed" ? "bg-red-500" :
                  task.status === "cancelled" ? "bg-gray-400" :
                  task.status === "completed" ? "bg-green-500" :
                  "bg-gradient-to-r from-amber-500 to-amber-600"
                }`}
                style={{ width: `${task.progress}%` }}
              />
            </div>
          </div>

          {/* 当前阶段时间线 */}
          {task.status === "running" && (
            <div className="border-t border-gray-100 pt-4">
              <p className="text-xs text-gray-500 mb-3">执行阶段</p>
              <div className="space-y-2">
                {["planner", "finance_search", "finance_knowledge", "report_synthesizer"].map((stage, idx) => {
                  const stageOrder = ["planner", "finance_search", "finance_knowledge", "report_synthesizer"];
                  const currentIdx = stageOrder.indexOf(task.current_stage);
                  const isDone = currentIdx > idx;
                  const isCurrent = currentIdx === idx;
                  return (
                    <div key={stage} className="flex items-center gap-3 text-sm">
                      <div
                        className={`w-5 h-5 rounded-full flex items-center justify-center ${
                          isDone ? "bg-green-500 text-white" :
                          isCurrent ? "bg-blue-500 text-white animate-pulse" :
                          "bg-gray-200 text-gray-400"
                        }`}
                      >
                        {isDone ? "✓" : isCurrent ? "•" : idx + 1}
                      </div>
                      <span className={
                        isDone ? "text-gray-700" :
                        isCurrent ? "text-blue-700 font-medium" :
                        "text-gray-400"
                      }>
                        {STAGE_LABELS[stage]}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 完成：跳转提示 */}
          {task.status === "completed" && task.result_report_id && (
            <div className="border-t border-gray-100 pt-4 flex items-center gap-2 text-sm text-green-600">
              <CheckCircle2 className="w-4 h-4" />
              报告已生成，2 秒后自动跳转
              <Link
                href={`/reports/${task.result_report_id}`}
                className="ml-auto flex items-center gap-1 px-3 py-1 bg-green-600 text-white rounded text-xs hover:bg-green-700"
              >
                立即查看
                <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
          )}

          {/* 失败：错误 + 重试 */}
          {task.status === "failed" && (
            <div className="border-t border-gray-100 pt-4">
              <div className="bg-red-50 border border-red-100 rounded-lg p-3 mb-3">
                <p className="text-xs text-red-600 font-medium mb-1">错误信息</p>
                <p className="text-sm text-red-700">{task.error_message || "未知错误"}</p>
              </div>
              <button
                onClick={handleRetry}
                className="w-full px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 flex items-center justify-center gap-2"
              >
                <RefreshCw className="w-4 h-4" />
                重新生成
              </button>
            </div>
          )}
        </div>

        {/* 任务详情 */}
        <div className="bg-white rounded-2xl shadow-sm p-6">
          <h2 className="text-sm font-medium text-gray-500 mb-3">任务详情</h2>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-500">任务 ID</dt>
              <dd className="text-gray-700 font-mono">{task.id}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">创建时间</dt>
              <dd className="text-gray-700">{new Date(task.created_at).toLocaleString("zh-CN")}</dd>
            </div>
            {task.started_at && (
              <div className="flex justify-between">
                <dt className="text-gray-500">开始时间</dt>
                <dd className="text-gray-700">{new Date(task.started_at).toLocaleString("zh-CN")}</dd>
              </div>
            )}
            {task.completed_at && (
              <div className="flex justify-between">
                <dt className="text-gray-500">完成时间</dt>
                <dd className="text-gray-700">{new Date(task.completed_at).toLocaleString("zh-CN")}</dd>
              </div>
            )}
            {task.result_report_id && (
              <div className="flex justify-between">
                <dt className="text-gray-500">报告 ID</dt>
                <dd>
                  <Link
                    href={`/reports/${task.result_report_id}`}
                    className="text-amber-600 hover:underline font-mono"
                  >
                    {task.result_report_id}
                  </Link>
                </dd>
              </div>
            )}
          </dl>
        </div>
      </main>
    </div>
  );
}
