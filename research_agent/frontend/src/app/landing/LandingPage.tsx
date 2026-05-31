'use client'

import { useEffect, useState, useMemo } from 'react'
import { ArrowRight, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

// 检查用户是否偏好减少动画
function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    setPrefersReducedMotion(mediaQuery.matches)

    const handler = (e: MediaQueryListEvent) => setPrefersReducedMotion(e.matches)
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }, [])

  return prefersReducedMotion
}

// 背景光晕组件
function BackgroundGlow({ reduced }: { reduced: boolean }) {
  if (reduced) return null

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {/* 主光晕 1 - 左上 */}
      <div
        className="absolute w-[800px] h-[800px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(251,191,36,0.25) 0%, rgba(251,191,36,0) 60%)',
          top: '-20%',
          left: '-10%',
          animation: 'glowFloat1 12s ease-in-out infinite',
        }}
      />
      {/* 主光晕 2 - 右下 */}
      <div
        className="absolute w-[600px] h-[600px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(217,119,6,0.2) 0%, rgba(217,119,6,0) 60%)',
          bottom: '-10%',
          right: '-5%',
          animation: 'glowFloat2 15s ease-in-out infinite',
        }}
      />
      {/* 装饰光晕 3 - 中间 */}
      <div
        className="absolute w-[400px] h-[400px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(168,162,158,0.3) 0%, rgba(168,162,158,0) 60%)',
          top: '40%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          animation: 'glowFloat3 18s ease-in-out infinite',
        }}
      />
      {/* 小光点 1 */}
      <div
        className="absolute w-[200px] h-[200px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(245,158,11,0.15) 0%, rgba(245,158,11,0) 60%)',
          top: '20%',
          right: '20%',
          animation: 'glowFloat1 10s ease-in-out infinite reverse',
        }}
      />
      {/* 小光点 2 */}
      <div
        className="absolute w-[150px] h-[150px] rounded-full"
        style={{
          background: 'radial-gradient(circle, rgba(251,146,60,0.2) 0%, rgba(251,146,60,0) 60%)',
          bottom: '30%',
          left: '15%',
          animation: 'glowFloat2 8s ease-in-out infinite reverse',
        }}
      />
    </div>
  )
}

// 粒子组件
function Particles({ reduced }: { reduced: boolean }) {
  const [particles, setParticles] = useState<Array<{id:number;size:number;x:number;y:number;duration:number;delay:number}>>([])

  useEffect(() => {
    if (reduced) return
    setParticles(Array.from({ length: 30 }, (_, i) => ({
      id: i,
      size: Math.random() * 6 + 2,
      x: Math.random() * 100,
      y: Math.random() * 100,
      duration: Math.random() * 15 + 10,
      delay: Math.random() * 8,
    })))
  }, [reduced])

  if (reduced || particles.length === 0) return null

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none">
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute rounded-full"
          style={{
            width: p.size,
            height: p.size,
            left: `${p.x}%`,
            top: `${p.y}%`,
            background: 'linear-gradient(135deg, rgba(251,191,36,0.6) 0%, rgba(217,119,6,0.4) 100%)',
            animation: `particleFloat ${p.duration}s ease-in-out infinite`,
            animationDelay: `${p.delay}s`,
          }}
        />
      ))}
    </div>
  )
}

// 装饰线条
function DecorativeLines({ reduced }: { reduced: boolean }) {
  if (reduced) return null

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none opacity-30">
      <svg
        className="absolute w-full h-full"
        viewBox="0 0 1920 1080"
        preserveAspectRatio="none"
      >
        <path
          d="M0,200 Q480,100 960,300 T1920,200"
          fill="none"
          stroke="url(#lineGradient)"
          strokeWidth="1"
          className="animate-pulse"
        />
        <path
          d="M0,600 Q480,500 960,700 T1920,600"
          fill="none"
          stroke="url(#lineGradient2)"
          strokeWidth="0.5"
          className="animate-pulse"
          style={{ animationDelay: '1s' }}
        />
        <defs>
          <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(251,191,36,0)" />
            <stop offset="50%" stopColor="rgba(251,191,36,0.5)" />
            <stop offset="100%" stopColor="rgba(251,191,36,0)" />
          </linearGradient>
          <linearGradient id="lineGradient2" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(217,119,6,0)" />
            <stop offset="50%" stopColor="rgba(217,119,6,0.3)" />
            <stop offset="100%" stopColor="rgba(217,119,6,0)" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  )
}

// 呼吸光晕按钮
function GlowButton({
  children,
  onClick,
  reduced,
}: {
  children: React.ReactNode
  onClick: () => void
  reduced: boolean
}) {
  return (
    <button
      onClick={onClick}
      aria-label="进入 Research Agent"
      className={cn(
        'group relative px-10 py-5 rounded-2xl font-semibold text-lg text-white',
        'overflow-hidden transition-all duration-300',
        'bg-gradient-to-r from-amber-600 to-amber-500',
        'hover:from-amber-500 hover:to-amber-400',
        'shadow-2xl shadow-amber-600/30 hover:shadow-amber-500/40',
        'cursor-pointer',
      )}
    >
      {/* 呼吸光晕 */}
      {!reduced && (
        <span
          className="absolute inset-0 rounded-2xl"
          style={{
            background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)',
            transform: 'translateX(-100%)',
            animation: 'glowPulse 2.5s ease-in-out infinite',
          }}
        />
      )}

      {/* 内容 */}
      <span className="relative z-10 flex items-center justify-center gap-3">
        {children}
      </span>
    </button>
  )
}

export default function LandingPage() {
  const [isLoaded, setIsLoaded] = useState(false)
  const prefersReducedMotion = usePrefersReducedMotion()

  useEffect(() => {
    const timer = setTimeout(() => setIsLoaded(true), 100)
    return () => clearTimeout(timer)
  }, [])

  const handleEnter = () => {
    window.location.href = '/chat'
  }

  return (
    <div className="min-h-screen relative overflow-hidden" style={{ background: '#faf8f5' }}>
      {/* 背景层 */}
      <BackgroundGlow reduced={prefersReducedMotion} />
      <Particles reduced={prefersReducedMotion} />
      <DecorativeLines reduced={prefersReducedMotion} />

      {/* 主内容 */}
      <div className="relative z-10 min-h-screen flex flex-col items-center justify-center px-6 py-20">
        {/* Logo + 标题区域 */}
        <div
          className="text-center mb-16"
          style={{
            opacity: isLoaded ? 1 : 0,
            transform: isLoaded ? 'translateY(0) scale(1)' : 'translateY(30px) scale(0.95)',
            transition: prefersReducedMotion ? 'none' : 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        >
          {/* Logo */}
          <div className="mb-8">
            <div
              className="inline-flex items-center justify-center w-24 h-24 rounded-3xl mx-auto"
              style={{
                background: 'linear-gradient(145deg, #d97706 0%, #f59e0b 50%, #fbbf24 100%)',
                boxShadow: '0 20px 60px rgba(217, 119, 6, 0.35), 0 8px 20px rgba(217, 119, 6, 0.25)',
              }}
            >
              <Sparkles className="w-12 h-12 text-white" />
            </div>
          </div>

          {/* 标题 */}
          <h1
            className="text-6xl md:text-7xl lg:text-8xl font-black tracking-tight text-stone-800 mb-6"
            style={{
              fontFamily: "'Crimson Pro', serif",
              letterSpacing: '-0.03em',
            }}
          >
            Research Agent
          </h1>

          {/* 副标题 */}
          <p
            className="text-xl md:text-2xl text-stone-500 max-w-xl mx-auto leading-relaxed"
            style={{
              fontFamily: "'Atkinson Hyperlegible', sans-serif",
            }}
          >
            智能研究助手，激活你的研究潜能
          </p>
        </div>

        {/* 三个特色标签 */}
        <div
          className="flex flex-wrap justify-center gap-4 mb-16"
          style={{
            opacity: isLoaded ? 1 : 0,
            transform: isLoaded ? 'translateY(0)' : 'translateY(20px)',
            transition: prefersReducedMotion ? 'none' : 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.2s',
          }}
        >
          {[
            { label: '智能搜索', color: 'bg-amber-50 text-amber-700 border-amber-200' },
            { label: '深度分析', color: 'bg-orange-50 text-orange-700 border-orange-200' },
            { label: '知识汇总', color: 'bg-stone-50 text-stone-700 border-stone-200' },
          ].map((tag) => (
            <span
              key={tag.label}
              className={cn(
                'px-5 py-2 rounded-full text-sm font-medium border',
                'backdrop-blur-sm',
                tag.color,
              )}
            >
              {tag.label}
            </span>
          ))}
        </div>

        {/* CTA 按钮 */}
        <div
          className="flex justify-center"
          style={{
            opacity: isLoaded ? 1 : 0,
            transform: isLoaded ? 'translateY(0)' : 'translateY(20px)',
            transition: prefersReducedMotion ? 'none' : 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.4s',
          }}
        >
          <GlowButton onClick={handleEnter} reduced={prefersReducedMotion}>
            <span>开始使用</span>
            <ArrowRight className="w-6 h-6 group-hover:translate-x-1 transition-transform" />
          </GlowButton>
        </div>

        {/* 底部留白 */}
        <div className="mt-20" />
      </div>
    </div>
  )
}
