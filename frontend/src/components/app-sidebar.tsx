import { useState } from "react"
import { Link, useLocation } from "react-router-dom"
import { Collapsible } from "radix-ui"
import {
  Camera,
  ChevronRight,
  Cpu,
  Crosshair,
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
  SidebarRail,
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
  const [calibrationOpen, setCalibrationOpen] = useState(
    pathname.startsWith("/calibration"),
  )
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const { data: cameras, isLoading: camerasLoading } = useCameras()

  return (
    <>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                asChild
                size="lg"
                tooltip="Neo Human Detector"
              >
                <Link to="/">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                    <Video className="size-4" />
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">Neo Human Detector</span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Điều hướng</SidebarGroupLabel>

            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    asChild
                    isActive={pathname === "/"}
                    tooltip="Dashboard"
                  >
                    <Link to="/">
                      <LayoutDashboard />
                      <span>Dashboard</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>

                <Collapsible.Root open={cameraOpen} onOpenChange={setCameraOpen}>
                  <SidebarMenuItem>
                    <Collapsible.Trigger asChild>
                      <SidebarMenuButton
                        isActive={pathname.startsWith("/cameras")}
                        className="pr-14"
                        title="Cameras"
                      >
                        <Camera />
                        <span>Cameras</span>
                        <ChevronRight
                          className={cn(
                            "absolute right-2 transition-transform duration-200 group-data-[collapsible=icon]:hidden",
                            cameraOpen && "rotate-90"
                          )}
                        />
                      </SidebarMenuButton>
                    </Collapsible.Trigger>

                    <SidebarMenuAction
                      title="Thêm camera"
                      className="right-7"
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

                <Collapsible.Root
                  open={calibrationOpen}
                  onOpenChange={setCalibrationOpen}
                >
                  <SidebarMenuItem>
                    <Collapsible.Trigger asChild>
                      <SidebarMenuButton
                        isActive={pathname.startsWith("/calibration")}
                        title="Calibration"
                      >
                        <Crosshair />
                        <span>Calibration</span>
                        <ChevronRight
                          className={cn(
                            "ml-auto transition-transform duration-200 group-data-[collapsible=icon]:hidden",
                            calibrationOpen && "rotate-90"
                          )}
                        />
                      </SidebarMenuButton>
                    </Collapsible.Trigger>

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
                                  isActive={
                                    pathname === `/calibration/cameras/${cam.id}`
                                  }
                                >
                                  <Link to={`/calibration/cameras/${cam.id}`}>
                                    {cam.name}
                                  </Link>
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
                    <SidebarMenuButton
                      asChild
                      isActive={pathname === item.url}
                      tooltip={item.title}
                    >
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

        <SidebarFooter>
          <p className="px-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
            v0.1.0
          </p>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>

      <AddCameraDialog open={addDialogOpen} onOpenChange={setAddDialogOpen} />
    </>
  )
}
