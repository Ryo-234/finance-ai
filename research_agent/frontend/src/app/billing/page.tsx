"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Spinner } from "@/components/Spinner";
import {
  ArrowLeft,
  Check,
  Sparkles,
  Zap,
  Building2,
  Crown,
  Clock,
  Loader2,
} from "lucide-react";

interface Plan {
  plan_type: string;
  name: string;
  monthly_price: number;
  monthly_reports: number;
  max_tokens_per_month: number;
  features: string[];
}

interface UsageInfo {
  reports_this_month: number;
  tokens_this_month: number;
  report_limit: number;
  token_limit: number;
}

const PLAN_ICONS: Record<string, any> = {
  free: Sparkles,
  pro: Zap,
  enterprise: Building2,
};

const PLAN_GRADIENTS: Record<string, string> = {
  free: "from-stone-50 to-stone-100",
  pro: "from-amber-50 to-orange-50",
  enterprise: "from-purple-50 to-indigo-50",
};

export default function BillingPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [usage, setUsage] = useState<UsageInfo | null>(null);
  const [currentPlan, setCurrentPlan] = useState<string>("free");
  const [loading, setLoading] = useState(true);
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("monthly");
  const [submitting, setSubmitting] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
      return;
    }
    loadData(token);
  }, [router]);

  const loadData = async (token: string) => {
    try {
      const [plansRes, usageRes, meRes] = await Promise.all([
        fetch("http://localhost:8001/api/billing/plans"),
        fetch("http://localhost:8001/api/billing/usage", {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch("http://localhost:8001/api/auth/me", {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);
      const plansData = await plansRes.json();
      const usageData = await usageRes.json();
      const meData = await meRes.json();
      setPlans(plansData);
      setUsage(usageData);
      setCurrentPlan(meData.plan_type || "free");
    } catch (err) {
      console.error("加载方案失败:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleUpgrade = async (planType: string) => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    if (planType === "free" || planType === currentPlan) return;

    setSubmitting(planType);
    try {
      const res = await fetch("http://localhost:8001/api/billing/orders", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ plan_type: planType, billing_cycle: billingCycle }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert("创建订单失败：" + (err.detail || "未知错误"));
        return;
      }
      const order = await res.json();
      router.push(`/billing/orders/${order.id}`);
    } catch (err: any) {
      alert("创建订单失败：" + err.message);
    } finally {
      setSubmitting(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Spinner className="w-8 h-8" style={{ color: "#d97706" }} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/chat"
              className="text-xl font-bold"
              style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}
            >
              金融投研 AI
            </Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-700">订阅升级</span>
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

      <main className="max-w-6xl mx-auto px-6 py-10">
        {/* 标题 */}
        <div className="text-center mb-8">
          <h1
            className="text-4xl font-bold text-gray-900 mb-3"
            style={{ fontFamily: "Crimson Pro, serif" }}
          >
            选择适合你的方案
          </h1>
          <p className="text-gray-500">从免费开始，按需升级 · 随时可取消</p>
        </div>

        {/* 当前用量 */}
        {usage && (
          <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-medium text-gray-500">本月用量</h2>
              <span className="px-2.5 py-1 bg-amber-50 text-amber-700 rounded-full text-xs font-medium">
                {currentPlan === "free"
                  ? "免费版"
                  : currentPlan === "pro"
                    ? "专业版"
                    : "企业版"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-gray-600">报告生成</span>
                  <span className="font-mono text-gray-900">
                    {usage.reports_this_month}
                    {usage.report_limit > 0 ? ` / ${usage.report_limit}` : " / ∞"}
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all"
                    style={{
                      width: `${
                        usage.report_limit > 0
                          ? Math.min(100, (usage.reports_this_month / usage.report_limit) * 100)
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between text-sm mb-1.5">
                  <span className="text-gray-600">Token 消耗</span>
                  <span className="font-mono text-gray-900">
                    {usage.tokens_this_month.toLocaleString()}
                    {usage.token_limit > 0
                      ? ` / ${(usage.token_limit / 1000).toFixed(0)}K`
                      : " / ∞"}
                  </span>
                </div>
                <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-amber-500 to-amber-600 transition-all"
                    style={{
                      width: `${
                        usage.token_limit > 0
                          ? Math.min(100, (usage.tokens_this_month / usage.token_limit) * 100)
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 月付/年付切换 */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex items-center bg-white border border-gray-200 rounded-full p-1 shadow-sm">
            <button
              onClick={() => setBillingCycle("monthly")}
              className={`px-5 py-1.5 text-sm rounded-full transition-colors ${
                billingCycle === "monthly"
                  ? "bg-amber-600 text-white"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              月付
            </button>
            <button
              onClick={() => setBillingCycle("yearly")}
              className={`px-5 py-1.5 text-sm rounded-full transition-colors flex items-center gap-1.5 ${
                billingCycle === "yearly"
                  ? "bg-amber-600 text-white"
                  : "text-gray-600 hover:text-gray-900"
              }`}
            >
              年付
              <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                省 20%
              </span>
            </button>
          </div>
        </div>

        {/* 方案卡片 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {plans.map((plan) => {
            const Icon = PLAN_ICONS[plan.plan_type] || Sparkles;
            const isCurrent = plan.plan_type === currentPlan;
            const isPaid = plan.monthly_price > 0;
            const price =
              billingCycle === "yearly"
                ? Math.round(plan.monthly_price * 12 * 0.8)
                : plan.monthly_price;
            const monthlyEquivalent =
              billingCycle === "yearly" ? Math.round(plan.monthly_price * 0.8) : plan.monthly_price;

            return (
              <div
                key={plan.plan_type}
                className={`relative rounded-2xl p-6 border-2 transition-all ${
                  plan.plan_type === "pro"
                    ? "border-amber-400 shadow-lg scale-105 bg-gradient-to-b " + PLAN_GRADIENTS[plan.plan_type]
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                {plan.plan_type === "pro" && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-amber-600 text-white text-xs font-medium rounded-full flex items-center gap-1">
                    <Crown className="w-3 h-3" />
                    推荐
                  </div>
                )}

                <div className="flex items-center gap-2 mb-3">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                      plan.plan_type === "free"
                        ? "bg-stone-100 text-stone-600"
                        : plan.plan_type === "pro"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-purple-100 text-purple-700"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>
                  <h3 className="text-lg font-semibold text-gray-900">{plan.name}</h3>
                </div>

                <div className="mb-4">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-bold text-gray-900">¥{price}</span>
                    <span className="text-sm text-gray-500">
                      / {billingCycle === "yearly" ? "年" : "月"}
                    </span>
                  </div>
                  {billingCycle === "yearly" && price > 0 && (
                    <p className="text-xs text-gray-400 mt-1">
                      相当于 ¥{monthlyEquivalent}/月
                    </p>
                  )}
                </div>

                <ul className="space-y-2 mb-6 text-sm">
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    {plan.monthly_reports < 0
                      ? "无限报告"
                      : `每月 ${plan.monthly_reports} 份报告`}
                  </li>
                  <li className="flex items-center gap-2 text-gray-700">
                    <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                    {plan.max_tokens_per_month < 0
                      ? "无限 Token"
                      : `每月 ${(plan.max_tokens_per_month / 1000).toFixed(0)}K Token`}
                  </li>
                  {plan.features.slice(0, 3).map((f) => (
                    <li key={f} className="flex items-center gap-2 text-gray-700">
                      <Check className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span className="text-xs">{featureLabel(f)}</span>
                    </li>
                  ))}
                </ul>

                <button
                  onClick={() => handleUpgrade(plan.plan_type)}
                  disabled={isCurrent || !isPaid || submitting !== null}
                  className={`w-full py-2.5 rounded-lg font-medium text-sm transition-all flex items-center justify-center gap-1.5 ${
                    isCurrent
                      ? "bg-gray-100 text-gray-500 cursor-default"
                      : !isPaid
                        ? "bg-gray-100 text-gray-500 cursor-default"
                        : plan.plan_type === "pro"
                          ? "bg-amber-600 text-white hover:bg-amber-700 shadow-sm"
                          : "bg-gray-900 text-white hover:bg-gray-800"
                  }`}
                >
                  {submitting === plan.plan_type ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      处理中...
                    </>
                  ) : isCurrent ? (
                    "当前方案"
                  ) : !isPaid ? (
                    "免费使用"
                  ) : (
                    "立即升级"
                  )}
                </button>
              </div>
            );
          })}
        </div>

        {/* 支付方式说明 */}
        <div className="mt-10 text-center">
          <p className="text-sm text-gray-500 mb-3">支持的支付方式</p>
          <div className="inline-flex items-center gap-3 bg-white border border-gray-200 rounded-full px-5 py-2 shadow-sm">
            <div className="flex items-center gap-1.5">
              <div
                className="w-6 h-6 rounded text-white text-xs font-bold flex items-center justify-center"
                style={{ background: "#1677ff" }}
              >
                支
              </div>
              <span className="text-sm text-gray-700">支付宝</span>
            </div>
            <span className="text-gray-300">|</span>
            <span className="text-xs text-gray-400">更多支付方式接入中</span>
          </div>
          <p className="text-xs text-gray-400 mt-4">
            支付完成后即时激活订阅 · 1 分钟内生效
          </p>
        </div>
      </main>
    </div>
  );
}

function featureLabel(feature: string): string {
  const labels: Record<string, string> = {
    unlimited_reports: "无限报告生成",
    advanced_templates: "高级报告模板",
    data_export: "PDF / Markdown 导出",
    api_access: "API 访问权限",
    custom_template: "自定义模板",
  };
  return labels[feature] || feature;
}
