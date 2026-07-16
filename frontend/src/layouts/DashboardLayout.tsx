import { Suspense } from "react"
import { Outlet } from "react-router-dom"
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { AppHeader } from "@/components/app-header"
import { Spinner } from "@/components/ui/spinner"

export function DashboardLayout() {
  return (
    <SidebarProvider>
      <AppSidebar />

      <main className="flex min-w-0 min-h-screen flex-1 flex-col">
        <AppHeader />

        <div className="flex-1 p-6">
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center">
                <Spinner className="size-6 text-muted-foreground" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </div>
      </main>
    </SidebarProvider>
  )
}
