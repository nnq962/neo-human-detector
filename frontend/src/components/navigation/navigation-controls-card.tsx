import { Card, CardContent } from "@/components/ui/card"
import { Switch } from "@/components/ui/switch"
import {
  PRIORITY_ENTRIES,
  STATUS_ENTRIES,
} from "@/components/navigation/navigation-task-view"
import { PriorityIcon } from "@/components/navigation/priority-icon"
import { cn } from "@/lib/utils"

interface NavigationControlsCardProps {
  showBboxes: boolean
  showZones: boolean
  onShowBboxesChange: (checked: boolean) => void
  onShowZonesChange: (checked: boolean) => void
}

export function NavigationControlsCard({
  showBboxes,
  showZones,
  onShowBboxesChange,
  onShowZonesChange,
}: NavigationControlsCardProps) {
  return (
    <Card>
      <CardContent className="p-4 sm:p-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="grid gap-4 lg:grid-cols-2">
            <section className="space-y-2.5">
              <p className="text-xs font-semibold tracking-wide text-foreground/70 uppercase">
                Ưu tiên task
              </p>
              <div className="flex flex-wrap gap-2">
                {PRIORITY_ENTRIES.map(([priority, view]) => (
                  <span
                    key={priority}
                    className="flex h-7 items-center gap-1.5 rounded-lg border bg-muted/30 px-2.5 text-xs text-muted-foreground"
                  >
                    <span className={cn("grid size-4 place-items-center rounded-full text-white", view.dotClassName)}>
                      <PriorityIcon priority={priority} className="size-3" />
                    </span>
                    <span>{view.label}</span>
                  </span>
                ))}
              </div>
            </section>

            <section className="space-y-2.5">
              <p className="text-xs font-semibold tracking-wide text-foreground/70 uppercase">
                Trạng thái task
              </p>
              <div className="flex flex-wrap gap-2">
                {STATUS_ENTRIES.map(([status, view]) => (
                  <span
                    key={status}
                    className="flex h-7 items-center gap-1.5 rounded-lg border bg-muted/30 px-2.5 text-xs text-muted-foreground"
                  >
                    <span className={cn("size-2 rounded-full", view.dotClassName)} />
                    {view.label}
                  </span>
                ))}
              </div>
            </section>
          </div>

          <section className="space-y-2.5 border-t pt-4 xl:min-w-64 xl:border-t-0 xl:border-l xl:pt-0 xl:pl-5">
            <p className="text-xs font-semibold tracking-wide text-foreground/70 uppercase">
              Lớp hiển thị
            </p>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2 text-sm transition-colors hover:bg-muted/60">
                <span>BBox</span>
                <Switch checked={showBboxes} onCheckedChange={onShowBboxesChange} />
              </label>
              <label className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border bg-muted/30 px-3 py-2 text-sm transition-colors hover:bg-muted/60">
                <span>Zones</span>
                <Switch checked={showZones} onCheckedChange={onShowZonesChange} />
              </label>
            </div>
          </section>
        </div>
      </CardContent>
    </Card>
  )
}
