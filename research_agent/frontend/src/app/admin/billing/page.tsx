"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Spinner } from "@/components/Spinner";
import {
  ArrowLeft,
  DollarSign,
  TrendingUp,
  Users,
  Receipt,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Clock,
  Search,
} from "lucide-react";

interface Order {
  id: string;
  order_no: string;
  user_id: string;
  plan_type: string;
  billing_cycle: string;
  amount_yuan: number;
  status: string;
  payment_method: string;
  transaction_id: string;
  paid_at: string | null;
  refund_amount: number;
  refund_reason: string;
  created_at: string;
}

interface Stats {
  total_paid_orders: number;
  total_gmv_yuan: number;
  today_paid_orders: number;
  today_gmv_yuan: number;
  refunded_orders: number;
  pending_orders: number;
}

const PLAN_LABELS: Record<string, string> = {
  free: "免费版",
  pro: "专业版",
  enterprise: "企业版",
};

const STATUS_CONFIG: Record<string, { label: string; bg: string; color: string; icon: any }> = {
  pending: { label: "待支付", bg: "bg-amber-50", color: "text-amber-700", icon: Clock },
  paid: { label: "已支付", bg: "bg-emerald-50", color: "text-emerald-700", icon: CheckCircle2 },
  cancelled: { label: "已取消", bg: "bg-gray-50", color: "text-gray-500", icon: XCircle },
  failed: { label: "失败", bg: "bg-red-50", color: "text-red-600", icon: AlertCircle },
  refunded: { label: "已退款", bg: "bg-gray-50", color: "text-gray-500", icon: Receipt },
};

export default function AdminBillingPage() {
  const router = useRouter();
  const [orders, setOrders] = useState<Order[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [refunding, setRefunding] = useState<string | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (!token) {
      router.push("/login");
      return;
    }
    loadData(token);
  }, [statusFilter, router]);

  const loadData = async (token: string) => {
    setLoading(true);
    try {
      const url =
        statusFilter === "all"
          ? "http://localhost:8001/api/admin/billing/orders?limit=200"
          : `http://localhost:8001/api/admin/billing/orders?status=${statusFilter}&limit=200`;
      const [ordersRes, statsRes] = await Promise.all([
        fetch(url, { headers: { Authorization: `Bearer ${token}` } }),
        fetch("http://localhost:8001/api/admin/billing/stats", {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (ordersRes.status === 403 || statsRes.status === 403) {
        alert("需要管理员权限");
        router.push("/dashboard");
        return;
      }

      const ordersData = await ordersRes.json();
      const statsData = await statsRes.json();
      setOrders(ordersData);
      setStats(statsData);
    } catch (err) {
      console.error("加载失败:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefund = async (order: Order) => {
    const amount = prompt(
      `退款金额（元）\n订单金额：¥${order.amount_yuan.toFixed(2)}\n留空为全额退款：`,
      order.amount_yuan.toFixed(2)
    );
    if (amount === null) return;

    const reason = prompt("退款原因：", "管理员手动退款");
    if (!reason) return;

    const token = localStorage.getItem("auth_token");
    if (!token) return;
    setRefunding(order.id);
    try {
      const body: any = { reason };
      const amt = parseFloat(amount);
      if (!isNaN(amt) && amt > 0 && amt !== order.amount_yuan) {
        body.refund_amount = amt;
      }
      const res = await fetch(
        `http://localhost:8001/api/admin/billing/orders/${order.id}/refund`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify(body),
        }
      );
      const data = await res.json();
      if (res.ok) {
        alert(`退款成功：¥${(data.refund_amount / 100).toFixed(2)}`);
        loadData(token);
      } else {
        alert("退款失败：" + (data.detail || "未知错误"));
      }
    } catch (err: any) {
      alert("退款失败：" + err.message);
    } finally {
      setRefunding(null);
    }
  };

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
            <span className="text-sm text-gray-700">管理员 · 订单管理</span>
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

      <main className="max-w-6xl mx-auto px-6 py-8">
        <h1
          className="text-2xl font-bold text-gray-900 mb-6"
          style={{ fontFamily: "Crimson Pro, serif" }}
        >
          订单管理后台
        </h1>

        {/* 统计卡片 */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard
              label="今日订单数"
              value={stats.today_paid_orders}
              icon={Receipt}
              color="amber"
            />
            <StatCard
              label="今日 GMV"
              value={`¥${stats.today_gmv_yuan.toFixed(2)}`}
              icon={DollarSign}
              color="emerald"
            />
            <StatCard
              label="总 GMV"
              value={`¥${stats.total_gmv_yuan.toFixed(2)}`}
              icon={TrendingUp}
              color="blue"
            />
            <StatCard
              label="待处理 / 退款"
              value={`${stats.pending_orders} / ${stats.refunded_orders}`}
              icon={AlertCircle}
              color="red"
            />
          </div>
        )}

        {/* 状态筛选 */}
        <div className="flex gap-2 mb-4 overflow-x-auto">
          {[
            { value: "all", label: "全部" },
            { value: "paid", label: "已支付" },
            { value: "pending", label: "待支付" },
            { value: "refunded", label: "已退款" },
            { value: "cancelled", label: "已取消" },
          ].map((f) => (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              className={`px-3.5 py-1.5 text-sm rounded-full transition-colors whitespace-nowrap ${
                statusFilter === f.value
                  ? "bg-amber-600 text-white"
                  : "bg-white text-gray-600 border border-gray-200 hover:border-amber-300"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* 订单表格 */}
        {loading ? (
          <div className="flex justify-center py-12">
            <Spinner className="w-8 h-8" style={{ color: "#d97706" }} />
          </div>
        ) : orders.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-100 p-12 text-center text-gray-500">
            暂无订单
          </div>
        ) : (
          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">订单号</th>
                  <th className="px-4 py-3 text-left font-medium">用户</th>
                  <th className="px-4 py-3 text-left font-medium">方案</th>
                  <th className="px-4 py-3 text-right font-medium">金额</th>
                  <th className="px-4 py-3 text-center font-medium">状态</th>
                  <th className="px-4 py-3 text-left font-medium">时间</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orders.map((o) => {
                  const cfg = STATUS_CONFIG[o.status] || STATUS_CONFIG.pending;
                  const Icon = cfg.icon;
                  return (
                    <tr key={o.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">
                        {o.order_no.slice(0, 16)}...
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500 font-mono">
                        {o.user_id.slice(0, 10)}...
                      </td>
                      <td className="px-4 py-3 text-gray-700">
                        {PLAN_LABELS[o.plan_type]}{" "}
                        <span className="text-xs text-gray-400">
                          ({o.billing_cycle === "yearly" ? "年" : "月"})
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono font-medium text-gray-900">
                        ¥{o.amount_yuan.toFixed(2)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${cfg.bg} ${cfg.color}`}
                        >
                          <Icon className="w-3 h-3" />
                          {cfg.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {new Date(o.created_at).toLocaleString("zh-CN", {
                          month: "2-digit",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {o.status === "paid" ? (
                          <button
                            onClick={() => handleRefund(o)}
                            disabled={refunding === o.id}
                            className="px-2.5 py-1 text-xs text-red-600 border border-red-200 rounded hover:bg-red-50 transition-colors disabled:opacity-50"
                          >
                            {refunding === o.id ? "处理中..." : "退款"}
                          </button>
                        ) : o.status === "refunded" ? (
                          <span className="text-xs text-gray-400">
                            已退 ¥{(o.refund_amount / 100).toFixed(2)}
                          </span>
                        ) : (
                          <span className="text-xs text-gray-300">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: any;
  icon: any;
  color: string;
}) {
  const colors: Record<string, string> = {
    amber: "bg-amber-50 text-amber-700",
    emerald: "bg-emerald-50 text-emerald-700",
    blue: "bg-blue-50 text-blue-700",
    red: "bg-red-50 text-red-700",
  };
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs text-gray-500">{label}</p>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${colors[color]}`}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
