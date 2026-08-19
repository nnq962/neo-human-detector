import { useMemo, useState } from "react"

import type { RobotTask } from "@/api/robot-tasks.api"
import { NavigationCameraCell } from "@/components/navigation/navigation-camera-cell"
import { NavigationControlsCard } from "@/components/navigation/navigation-controls-card"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useCameras } from "@/hooks/use-cameras"
import { useRobotTasks } from "@/hooks/use-robot-tasks"
import { cn } from "@/lib/utils"

const EMPTY_RUNTIME_TASKS: RobotTask[] = []

export function NavigationPage() {
  const { data: cameras = [], isLoading: camerasLoading } = useCameras()
  const { snapshot: taskSnapshot } = useRobotTasks()
  const [showBboxes, setShowBboxes] = useState(false)
  const [showZones, setShowZones] = useState(false)
  const runtimeTasks = taskSnapshot?.tasks ?? EMPTY_RUNTIME_TASKS
  const tasksByCamera = useMemo(() => {
    const groupedTasks = new Map<string, RobotTask[]>()
    for (const task of runtimeTasks) {
      const cameraTasks = groupedTasks.get(task.camera_id)
      if (cameraTasks) cameraTasks.push(task)
      else groupedTasks.set(task.camera_id, [task])
    }
    return groupedTasks
  }, [runtimeTasks])
  const singleCamera = cameras.length === 1

  return (
    <div className="space-y-4">
      <NavigationControlsCard
        showBboxes={showBboxes}
        showZones={showZones}
        onShowBboxesChange={setShowBboxes}
        onShowZonesChange={setShowZones}
      />

      <Card>
        <CardHeader>
          <CardTitle>Cameras</CardTitle>
        </CardHeader>
        <CardContent>
          {camerasLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Skeleton className="aspect-video rounded-lg" />
              <Skeleton className="aspect-video rounded-lg" />
            </div>
          ) : cameras.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              Chưa có camera nào.
            </p>
          ) : (
            <div
              className={cn(
                "grid grid-cols-1 gap-4",
                singleCamera ? "mx-auto w-full max-w-4xl" : "sm:grid-cols-2",
              )}
            >
              {cameras.map((camera) => (
                <NavigationCameraCell
                  key={camera.id}
                  camera={camera}
                  runtimeTasks={tasksByCamera.get(camera.id) ?? EMPTY_RUNTIME_TASKS}
                  showBboxes={showBboxes}
                  showZones={showZones}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
