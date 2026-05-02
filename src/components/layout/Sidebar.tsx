'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, Briefcase, BarChart2, Settings, ChevronLeft, ChevronRight, X, Zap,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { useUIStore } from '@/stores/useUIStore'
import { FavoriteStocks } from '@/components/search/FavoriteStocks'

const navItems = [
  { label: '儀表板', href: '/dashboard', icon: LayoutDashboard },
  { label: '當沖監測', href: '/daytrade', icon: Zap },
  { label: '模擬倉', href: '/portfolio', icon: Briefcase },
  { label: '歷史統計', href: '/statistics', icon: BarChart2 },
  { label: '設定', href: '/settings', icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()
  const { sidebarOpen, toggleSidebar, mobileSidebarOpen, setMobileSidebarOpen } = useUIStore()

  const navContent = (compact: boolean) => (
    <nav className="flex flex-col gap-1 p-2">
      {navItems.map((item) => {
        const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMobileSidebarOpen(false)}
            className={cn(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
              isActive
                ? 'bg-primary/10 text-primary font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
            )}
          >
            <item.icon className="h-5 w-5 shrink-0" />
            {!compact && <span>{item.label}</span>}
          </Link>
        )
      })}
    </nav>
  )

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className={cn(
          'hidden border-r bg-card transition-all duration-300 lg:flex lg:flex-col',
          sidebarOpen ? 'lg:w-60' : 'lg:w-16'
        )}
      >
        <div className="flex h-16 items-center justify-between border-b px-4">
          {sidebarOpen && (
            <span className="text-sm font-semibold text-muted-foreground">導覽</span>
          )}
          <Button variant="ghost" size="icon" onClick={toggleSidebar} className="h-8 w-8">
            {sidebarOpen ? <ChevronLeft className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </Button>
        </div>

        <ScrollArea className="flex-1">
          {navContent(!sidebarOpen)}

          {sidebarOpen && (
            <>
              <Separator className="mx-2 my-2" />
              <div className="p-2">
                <FavoriteStocks />
              </div>
            </>
          )}
        </ScrollArea>

        <div className="border-t p-2">
          <p className="text-center text-xs text-muted-foreground">
            {sidebarOpen ? '僅供實驗研究使用' : ''}
          </p>
        </div>
      </aside>

      {/* Mobile sidebar overlay */}
      {mobileSidebarOpen && (
        <>
          <div
            className="fixed inset-0 z-50 bg-black/50 lg:hidden"
            onClick={() => setMobileSidebarOpen(false)}
          />
          <aside className="fixed inset-y-0 left-0 z-50 w-64 border-r bg-card shadow-lg lg:hidden">
            <div className="flex h-16 items-center justify-between border-b px-4">
              <span className="text-sm font-semibold">導覽</span>
              <Button variant="ghost" size="icon" onClick={() => setMobileSidebarOpen(false)} className="h-8 w-8">
                <X className="h-4 w-4" />
              </Button>
            </div>
            <ScrollArea className="flex-1">
              {navContent(false)}
              <Separator className="mx-2 my-2" />
              <div className="p-2">
                <FavoriteStocks />
              </div>
            </ScrollArea>
          </aside>
        </>
      )}
    </>
  )
}
