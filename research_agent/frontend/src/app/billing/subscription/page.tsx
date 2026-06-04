"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Spinner } from "@/components/Spinner";
import { ArrowLeft, Crown, Zap, Building2, AlertTriangle, CheckCircle2 } from "lucide-react";

interface CurrentSubscription {
  plan_type: string;
  billing_cycle: string;
  status: string;
  expires_at: string;
  auto_renew: boolean;
  started_at: string;
}

const PLAN_INFO: Record<string, { name: string; icon: any; color: string }> = {
  free: { name: "免费版", icon: Zap, color: "text-stone-600 bg-stone-50" },
  pro: { name: "专业版", icon: Crown, color: "text-amber-700 bg-amber-50" },
  enterprise: { name: "企业版", icon: Building2, color: "text-purple-700 bg-purple-50" },
};

export default function SubscriptionPage() {
  const router = useRouter();
  const [sub, setSub] = useState<CurrentSubscription | null>(null);
  const [loading, setLoading] = useState(true);
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
      return;
    }
    loadSub(token);
  }, [router]);

  const loadSub = async (token: string) => {
    try {
      const res = await fetch("http://localhost:8001/api/billing/subscription/current", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 404) {
        setSub(null);
      } else if (res.ok) {
        const data = await res.json();
        setSub(data);
      }
    } catch (err) {
      console.error("加载订阅失败:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!confirm("确定取消订阅？取消后将立即降级为免费版，已支付部分不退还。")) return;
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    setCanceling(true);
    try {
      const res = await fetch("http://localhost:8001/api/billing/subscription/cancel", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.ok) {
        alert("订阅已取消");
        router.push("/billing");
      } else {
        alert("取消失败");
      }
    } catch (err: any) {
      alert("取消失败：" + err.message);
    } finally {
      setCanceling(false);
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
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/chat"
              className="text-xl font-bold"
              style={{ fontFamily: "Crimson Pro, serif", color: "#d97706" }}
            >
              金融投研 AI
            </Link>
            <span className="text-gray-300">/</span>
            <Link href="/billing" className="text-sm text-gray-500 hover:text-gray-700">
              订阅升级
            </Link>
            <span className="text-gray-300">/</span>
            <span className="text-sm text-gray-700">订阅管理</span>
          </div>
          <Link
            href="/billing"
            className="text-sm text-gray-500 hover:text-amber-600 transition-colors flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" />
            返回
          </Link>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-8">
        <h1
          className="text-2xl font-bold text-gray-900 mb-6"
          style={{ fontFamily: "Crimson Pro, serif" }}
        >
          订阅管理
        </h1>

        {!sub || sub.plan_type === "free" ? (
          <div className="bg-white rounded-2xl border border-gray-100 p-12 text-center">
            <div className="w-16 h-16 rounded-full bg-stone-50 flex items-center justify-center mx-auto mb-4">
              <Zap className="w-8 h-8 text-stone-400" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">当前为免费版</h2>
            <p className="text-sm text-gray-500 mb-6">升级到专业版，解锁无限报告和高级功能</p>
            <Link
              href="/billing"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700 transition-colors"
            >
              <Crown className="w-4 h-4" />
              立即升级
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {/* 当前订阅卡片 */}
            <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl p-6 border border-amber-100">
              <div className="flex items-center gap-3 mb-4">
                <div
                  className={`w-12 h-12 rounded-xl flex items-center justify-center ${PLAN_INFO[sub.plan_type].color}`}
                >
                  {(() => {
                    const Icon = PLAN_INFO[sub.plan_type].icon;
                    return <Icon className="w-6 h-6" />;
                  })()}
                </div>
                <div>
                  <h2 className="text-xl font-bold text-gray-900">
                    {PLAN_INFO[sub.plan_type].name}
                  </h2>
                  <p className="text-xs text-gray-500">
                    {sub.billing_cycle === "yearly" ? "年付订阅" : "月付订阅"}
                  </p>
                </div>
                <div className="ml-auto flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-700 rounded-full text-xs font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  订阅生效中
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 mt-5 pt-5 border-t border-amber-200/50">
                <div>
                  <p className="text-xs text-gray-500 mb-1">生效时间</p>
                  <p className="text-sm font-medium text-gray-900">
                    {new Date(sub.started_at).toLocaleDateString("zh-CN")}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 mb-1">到期时间</p>
                  <p className="text-sm font-medium text-gray-900">
                    {new Date(sub.expires_at).toLocaleDateString("zh-CN")}
                  </p>
                </div>
              </div>
            </div>

            {/* 取消订阅 */}
            <div className="bg-white rounded-2xl border border-red-100 p-6">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" />
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900 mb-1">取消订阅</h3>
                  <p className="text-xs text-gray-500 mb-4">
                    取消后将立即降级为免费版，已支付部分不退还。
                  </p>
                  <button
                    onClick={handleCancel}
                    disabled={canceling}
                    className="px-4 py-1.5 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    {canceling ? "处理中..." : "取消订阅"}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
