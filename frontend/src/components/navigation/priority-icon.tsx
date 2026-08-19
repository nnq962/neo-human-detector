import { Armchair, ChevronUp, ChevronsUp } from "lucide-react"

import type { NavigationTaskPriority } from "@/lib/navigation-tasks"

export function PriorityIcon({
  priority,
  className,
}: {
  priority: NavigationTaskPriority
  className?: string
}) {
  if (priority === "low") {
    return <Armchair className={className} strokeWidth={2.5} />
  }
  if (priority === "medium") {
    return <ChevronUp className={className} strokeWidth={3} />
  }
  return <ChevronsUp className={className} strokeWidth={3} />
}
