import { Outlet } from "react-router-dom"
import { SidebarProvider } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { AppHeader } from "@/components/app-header"

export function DashboardLayout() {
  return (
    <SidebarProvider>
      <AppSidebar />

      <main className="flex min-h-screen flex-1 flex-col">
        <AppHeader />

        <div className="flex-1 p-6">
          <Outlet />
        </div>
      </main>
    </SidebarProvider>
  )
}
