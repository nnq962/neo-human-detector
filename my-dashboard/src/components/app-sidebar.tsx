import { useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { Collapsible } from "radix-ui"
import {
  Camera,
  ChevronRight,
  Cpu,
  Fingerprint,
  GitBranch,
  LayoutDashboard,
  Plus,
  ScanEye,
  Video,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar"
import { useCameras } from "@/hooks/use-cameras"
import { AddCameraDialog } from "@/components/add-camera-dialog"

const navItems = [
  { title: "Detection", url: "/detection", icon: ScanEye },
  { title: "Zone State Machine", url: "/zone-state-machine", icon: GitBranch },
  { title: "Re-ID", url: "/re-id", icon: Fingerprint },
  { title: "UART", url: "/uart", icon: Cpu },
]

export function AppSidebar() {
  const { pathname } = useLocation()
  const [cameraOpen, setCameraOpen] = useState(pathname.startsWith("/cameras"))
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const { data: cameras, isLoading: camerasLoading } = useCameras()

  return (
    <>
      <Sidebar>
        <SidebarHeader className="p-4">
          <div className="flex items-center gap-2">
            <Video className="size-5 shrink-0" />
            <span className="text-sm font-semibold">Neo Human Detector</span>
          </div>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Điều hướng</SidebarGroupLabel>

            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={pathname === "/"}>
                    <Link to="/">
                      <LayoutDashboard />
                      <span>Dashboard</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>

                <Collapsible.Root open={cameraOpen} onOpenChange={setCameraOpen}>
                  <SidebarMenuItem>
                    <Collapsible.Trigger asChild>
                      <SidebarMenuButton isActive={pathname.startsWith("/cameras")}>
                        <Camera />
                        <span>Cameras</span>
                        <ChevronRight
                          className={cn(
                            "ml-auto transition-transform duration-200",
                            cameraOpen && "rotate-90"
                          )}
                        />
                      </SidebarMenuButton>
                    </Collapsible.Trigger>

                    <SidebarMenuAction
                      showOnHover
                      title="Thêm camera"
                      onClick={(e) => {
                        e.stopPropagation()
                        setAddDialogOpen(true)
                      }}
                    >
                      <Plus />
                    </SidebarMenuAction>

                    <Collapsible.Content>
                      {(camerasLoading || (cameras && cameras.length > 0)) && (
                        <SidebarMenuSub>
                          {camerasLoading ? (
                            <>
                              <SidebarMenuSkeleton />
                              <SidebarMenuSkeleton />
                            </>
                          ) : (
                            cameras?.map((cam) => (
                              <SidebarMenuSubItem key={cam.id}>
                                <SidebarMenuSubButton
                                  asChild
                                  isActive={pathname === `/cameras/${cam.id}`}
                                >
                                  <Link to={`/cameras/${cam.id}`}>{cam.name}</Link>
                                </SidebarMenuSubButton>
                              </SidebarMenuSubItem>
                            ))
                          )}
                        </SidebarMenuSub>
                      )}
                    </Collapsible.Content>
                  </SidebarMenuItem>
                </Collapsible.Root>

                {navItems.map((item) => (
                  <SidebarMenuItem key={item.url}>
                    <SidebarMenuButton asChild isActive={pathname === item.url}>
                      <Link to={item.url}>
                        <item.icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter className="p-4 text-xs text-muted-foreground">
          v0.1.0
        </SidebarFooter>
      </Sidebar>

      <AddCameraDialog open={addDialogOpen} onOpenChange={setAddDialogOpen} />
    </>
  )
}
