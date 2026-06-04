"use client";

import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Spinner } from "@/components/Spinner";
import { EmptyState } from "@/components/EmptyState";
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  Clock,
  Receipt,
  AlertCircle,
  FileText,
} from "lucide-react";

interface Order {
  id: string;
  order_no: string;
  plan_type: string;
  billing_cycle: string;
  amount_yuan: number;
  status: string;
  created_at: string;
  paid_at: string | null;
  refund_amount: number;
}

const PLAN_LABELS: Record<string, string> = {
  free: "免费版",
  pro: "专业版",
  enterprise: "企业版",
};

const STATUS_CONFIG: Record<
  string,
  { label: string; bg: string; color: string; icon: any }
> = {
  pending: {
    label: "等待支付",
    bg: "bg-amber-50",
    color: "text-amber-700",
    icon: Clock,
  },
  paid: {
    label: "支付成功",
    bg: "bg-emerald-50",
    color: "text-emerald-700",
    icon: CheckCircle2,
  },
  cancelled: {
    label: "已取消",
    bg: "bg-gray-50",
    color: "text-gray-500",
    icon: XCircle,
  },
  failed: {
    label: "支付失败",
    bg: "bg-red-50",
    color: "text-red-600",
    icon: AlertCircle,
  },
  refunded: {
    label: "已退款",
    bg: "bg-gray-50",
    color: "text-gray-500",
    icon: Receipt,
  },
};

const FILTERS: { value: string; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "paid", label: "已支付" },
  { value: "pending", label: "待支付" },
  { value: "cancelled", label: "已取消" },
  { value: "refunded", label: "已退款" },
];

export default function OrdersPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    if (searchParams.get("success") === "1") {
      alert("支付成功！");
    }
  }, [searchParams]);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
      return;
    }
    loadOrders(token);
  }, [filter, router]);

  const loadOrders = async (token: string) => {
    setLoading(true);
    try {
      const url =
        filter === "all"
          ? "http://localhost:8001/api/billing/orders?limit=50"
          : `http://localhost:8001/api/billing/orders?status=${filter}&limit=50`;
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      setOrders(data);
    } catch (err) {
      console.error("加载订单失败:", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-white border-b border-gray-100 sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 h-14 flex items-center justify-between">
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
            <span className="text-sm text-gray-700">订单历史</span>
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

      <main className="max-w-5xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1
            className="text-2xl font-bold text-gray-900"
            style={{ fontFamily: "Crimson Pro, serif" }}
          >
            订单历史
          </h1>
          <Link
            href="/billing"
            className="px-4 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 transition-colors"
          >
            升级订阅
          </Link>
        </div>

        {/* 状态筛选 */}
        <div className="flex gap-2 mb-5 overflow-x-auto">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              onClick={() => setFilter(f.value)}
              className={`px-3.5 py-1.5 text-sm rounded-full transition-colors whitespace-nowrap ${
                filter === f.value
                  ? "bg-amber-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:border-amber-300"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner className="w-8 h-8" style={{ color: "#d97706" }} />
          </div>
        ) : orders.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-100">
            <EmptyState
              icon={<FileText className="w-12 h-12" />}
              title="暂无订单"
              description="还没有任何订单记录"
              action={
                <Link
                  href="/billing"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 transition-colors"
                >
                  升级订阅
                </Link>
              }
            />
          </div>
        ) : (
          <div className="space-y-3">
            {orders.map((order) => {
              const cfg = STATUS_CONFIG[order.status] || STATUS_CONFIG.pending;
              const Icon = cfg.icon;
              return (
                <Link
                  key={order.id}
                  href={`/billing/orders/${order.id}`}
                  className="block bg-white rounded-xl border border-gray-100 p-5 hover:border-amber-200 hover:shadow-sm transition-all"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="font-semibold text-gray-900">
                          {PLAN_LABELS[order.plan_type]}订阅
                        </span>
                        <span className="text-xs text-gray-400">
                          {order.billing_cycle === "yearly" ? "年付" : "月付"}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 font-mono">
                        {order.order_no}
                      </p>
                    </div>
                    <div className="text-right ml-4 shrink-0">
                      <p className="text-xl font-bold text-gray-900 mb-1">
                        ¥{order.amount_yuan.toFixed(2)}
                      </p>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${cfg.bg} ${cfg.color}`}
                      >
                        <Icon className="w-3 h-3" />
                        {cfg.label}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>下单时间：{new Date(order.created_at).toLocaleString("zh-CN")}</span>
                    {order.paid_at && (
                      <span>支付时间：{new Date(order.paid_at).toLocaleString("zh-CN")}</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
