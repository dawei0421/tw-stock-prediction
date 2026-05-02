'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { LayoutDashboard, Briefcase, BarChart2, Settings, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'

const navItems = [
  { label: '首頁', href: '/dashboard', icon: LayoutDashboard },
  { label: '當沖', href: '/daytrade', icon: Zap },
  { label: '模擬倉', href: '/portfolio', icon: Briefcase },
  { label: '統計', href: '/statistics', icon: BarChart2 },
  { label: '設定', href: '/settings', icon: Settings },
]

export function MobileNav() {
  const pathname = usePathname()

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 border-t bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 lg:hidden">
      <div className="flex h-14 items-center justify-around">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex flex-col items-center gap-0.5 px-3 py-1 text-xs',
                isActive ? 'text-primary' : 'text-muted-foreground'
              )}
            >
              <item.icon className="h-5 w-5" />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
