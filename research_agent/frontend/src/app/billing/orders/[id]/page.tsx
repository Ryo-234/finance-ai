"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import QRCode from "react-qr-code";
import { Spinner } from "@/components/Spinner";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  RefreshCw,
  XCircle,
  Loader2,
  Copy,
} from "lucide-react";

interface Order {
  id: string;
  order_no: string;
  plan_type: string;
  billing_cycle: string;
  amount_yuan: number;
  status: string;
  qr_code_url: string;
  expired_at: string;
  paid_at: string | null;
  created_at: string;
}

const PLAN_LABELS: Record<string, string> = {
  free: "免费版",
  pro: "专业版",
  enterprise: "企业版",
};

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  pending: { label: "等待支付", color: "text-amber-600" },
  paid: { label: "支付成功", color: "text-emerald-600" },
  cancelled: { label: "已取消", color: "text-gray-500" },
  failed: { label: "支付失败", color: "text-red-600" },
  refunded: { label: "已退款", color: "text-gray-500" },
};

export default function OrderPaymentPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [now, setNow] = useState(Date.now());
  const [polling, setPolling] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);
  const tickRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
      return;
    }
    loadOrder(token);

    // 倒计时
    tickRef.current = setInterval(() => setNow(Date.now()), 1000);

    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [params.id, router]);

  // 订单状态变化或首次加载后启动轮询
  useEffect(() => {
    if (order?.status === "pending" && !pollRef.current) {
      startPolling();
    }
    if (order && order.status !== "pending" && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [order?.status]);

  const loadOrder = async (token: string, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await fetch(`http://localhost:8001/api/billing/orders/${params.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        if (res.status === 404) {
          alert("订单不存在");
          router.push("/billing");
          return;
        }
        if (res.status === 403) {
          alert("无权访问该订单");
          router.push("/billing");
          return;
        }
        throw new Error("加载失败");
      }
      const data = await res.json();
      setOrder(data);

      // 已支付：3 秒后自动跳转
      if (data.status === "paid") {
        setTimeout(() => router.push("/billing?paid=1"), 3000);
      }
    } catch (err: any) {
      console.error("加载订单失败:", err);
      alert("加载订单失败：" + err.message);
    } finally {
      setLoading(false);
    }
  };

  const startPolling = () => {
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    setPolling(true);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(
          `http://localhost:8001/api/billing/orders/${params.id}/refresh`,
          { method: "POST", headers: { Authorization: `Bearer ${token}` } }
        );
        const data = await res.json();
        if (data.status === "paid") {
          // 主动查询命中：刷新订单
          await loadOrder(token, true);
        }
      } catch (err) {
        console.error("轮询失败:", err);
      }
    }, 3000);
  };

  const handleMockPay = async () => {
    if (!confirm("⚠️ 开发模式：模拟支付成功，绕过支付宝\n确认要继续吗？")) return;
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    try {
      const res = await fetch(
        `http://localhost:8001/api/billing/orders/${params.id}/mock-pay`,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } }
      );
      const data = await res.json();
      if (res.ok) {
        alert("✅ " + data.message);
        await loadOrder(token, true);
        if (data.status === "paid") {
          setTimeout(() => router.push("/billing?paid=1"), 1500);
        }
      } else {
        alert("失败：" + (data.detail || "未知错误"));
      }
    } catch (err: any) {
      alert("错误：" + err.message);
    }
  };

  const handleCancel = async () => {
    if (!confirm("确定取消该订单？")) return;
    const token = localStorage.getItem("auth_token");
    if (!token) return;
    try {
      await fetch(`http://localhost:8001/api/billing/orders/${params.id}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      await loadOrder(token, true);
    } catch (err: any) {
      alert("取消失败：" + err.message);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <Spinner className="w-8 h-8" style={{ color: "#d97706" }} />
      </div>
    );
  }

  if (!order) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-500">订单不存在</p>
      </div>
    );
  }

  // 计算倒计时
  const expiredAt = new Date(order.expired_at).getTime();
  const remaining = Math.max(0, Math.floor((expiredAt - now) / 1000));
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");
  const isExpired = remaining === 0 && order.status === "pending";
  const statusInfo = STATUS_LABELS[order.status] || STATUS_LABELS.pending;

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link
              href="/billing"
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
            <span className="text-sm text-gray-700">订单支付</span>
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
        {order.status === "paid" ? (
          <PaidCard order={order} />
        ) : (
          <>
            {/* 订单信息 */}
            <div className="bg-white rounded-2xl shadow-sm p-6 mb-5">
              <div className="flex items-center justify-between mb-3">
                <h1 className="text-xl font-semibold text-gray-900">订单详情</h1>
                <span className={`text-sm font-medium ${statusInfo.color}`}>
                  {statusInfo.label}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-500 mb-1">订单号</p>
                  <p className="font-mono text-gray-900 flex items-center gap-1">
                    {order.order_no}
                    <CopyButton text={order.order_no} />
                  </p>
                </div>
                <div>
                  <p className="text-gray-500 mb-1">订阅方案</p>
                  <p className="text-gray-900">
                    {PLAN_LABELS[order.plan_type]}{" "}
                    <span className="text-xs text-gray-400">
                      ({order.billing_cycle === "yearly" ? "年付" : "月付"})
                    </span>
                  </p>
                </div>
                <div>
                  <p className="text-gray-500 mb-1">支付金额</p>
                  <p className="text-2xl font-bold text-amber-600">
                    ¥{order.amount_yuan.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-gray-500 mb-1">创建时间</p>
                  <p className="text-gray-900 text-xs">
                    {new Date(order.created_at).toLocaleString("zh-CN")}
                  </p>
                </div>
              </div>
            </div>

            {/* 支付二维码 */}
            <div className="bg-white rounded-2xl shadow-sm p-8 text-center">
              {!isExpired && order.status === "pending" ? (
                <>
                  <div className="flex items-center justify-center gap-2 mb-4">
                    <Clock className="w-4 h-4 text-amber-600" />
                    <span className="text-sm text-amber-600 font-mono font-medium">
                      剩余时间 {mm}:{ss}
                    </span>
                  </div>

                  {order.qr_code_url ? (
                    <>
                      <div className="inline-block p-4 bg-white border-2 border-gray-100 rounded-xl mb-4">
                        <QRCode
                          value={order.qr_code_url}
                          size={220}
                          style={{ height: "auto", maxWidth: "100%", width: "100%" }}
                        />
                      </div>
                      <p className="text-sm text-gray-700 mb-1">使用支付宝扫一扫</p>
                      <p className="text-xs text-gray-400 mb-6">完成支付后页面将自动跳转</p>
                    </>
                  ) : (
                    <div className="py-12">
                      <XCircle className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                      <p className="text-sm text-gray-600 mb-1">支付暂不可用</p>
                      <p className="text-xs text-gray-400 mb-4">
                        管理员未配置支付宝沙箱，请联系管理员
                      </p>
                    </div>
                  )}

                  <div className="flex items-center justify-center gap-3 text-xs text-gray-400">
                    <div className="flex items-center gap-1">
                      {polling ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <CheckCircle2 className="w-3 h-3" />
                      )}
                      自动检测支付状态
                    </div>
                  </div>

                  <div className="mt-6 pt-6 border-t border-gray-100 flex justify-center gap-3 flex-wrap">
                    <button
                      onClick={() => {
                        const token = localStorage.getItem("auth_token");
                        if (token) loadOrder(token, true);
                      }}
                      className="px-4 py-1.5 text-xs text-gray-600 border border-gray-200 rounded-lg hover:border-amber-300 hover:text-amber-700 transition-colors flex items-center gap-1"
                    >
                      <RefreshCw className="w-3 h-3" />
                      已支付？刷新状态
                    </button>
                    <button
                      onClick={handleMockPay}
                      className="px-4 py-1.5 text-xs text-emerald-700 border border-emerald-200 rounded-lg hover:bg-emerald-50 transition-colors"
                      title="开发模式：绕过支付宝，模拟支付成功"
                    >
                      ⚙️ 模拟支付（开发模式）
                    </button>
                    <button
                      onClick={handleCancel}
                      className="px-4 py-1.5 text-xs text-red-600 border border-red-100 rounded-lg hover:bg-red-50 transition-colors"
                    >
                      取消订单
                    </button>
                  </div>
                </>
              ) : (
                <div className="py-8">
                  <XCircle className="w-16 h-16 text-gray-300 mx-auto mb-3" />
                  <h3 className="text-lg font-semibold text-gray-700 mb-2">
                    订单已{statusInfo.label.replace("已", "")}
                  </h3>
                  <p className="text-sm text-gray-500 mb-6">
                    {order.status === "cancelled"
                      ? "该订单已被取消"
                      : "订单已过期，请重新下单"}
                  </p>
                  <button
                    onClick={() => router.push("/billing")}
                    className="px-5 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 transition-colors"
                  >
                    返回订阅页
                  </button>
                </div>
              )}
            </div>

            {/* 支付说明 */}
            <div className="mt-5 text-center text-xs text-gray-400 space-y-1">
              <p>· 支付完成后，订阅将自动激活</p>
              <p>· 如有问题，请联系客服</p>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function PaidCard({ order }: { order: Order }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm p-12 text-center">
      <div className="w-20 h-20 rounded-full bg-emerald-50 flex items-center justify-center mx-auto mb-4">
        <CheckCircle2 className="w-12 h-12 text-emerald-500" />
      </div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">支付成功</h1>
      <p className="text-gray-500 mb-6">
        您的 {PLAN_LABELS[order.plan_type]} 订阅已激活
      </p>
      <div className="bg-gray-50 rounded-xl p-4 mb-6 inline-block">
        <p className="text-sm text-gray-600">订单金额</p>
        <p className="text-3xl font-bold text-amber-600 mt-1">
          ¥{order.amount_yuan.toFixed(2)}
        </p>
      </div>
      <div className="flex justify-center gap-3">
        <Link
          href="/dashboard"
          className="px-5 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 transition-colors"
        >
          立即体验
        </Link>
        <Link
          href="/billing/subscription"
          className="px-5 py-2 border border-gray-200 text-gray-600 rounded-lg text-sm hover:border-amber-300 hover:text-amber-700 transition-colors"
        >
          查看订阅
        </Link>
      </div>
      <p className="text-xs text-gray-400 mt-6">3 秒后自动跳转...</p>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="p-0.5 hover:bg-gray-100 rounded transition-colors"
      title="复制订单号"
    >
      {copied ? (
        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
      ) : (
        <Copy className="w-3 h-3 text-gray-400" />
      )}
    </button>
  );
}
