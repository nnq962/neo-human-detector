import type {
  NavigationTaskPriority,
  NavigationTaskStatus,
} from "@/lib/navigation-tasks"

export const PRIORITY_VIEW: Record<NavigationTaskPriority, {
  label: string
  dotClassName: string
  badgeClassName: string
}> = {
  low: {
    label: "Thấp",
    dotClassName: "bg-emerald-500",
    badgeClassName: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  medium: {
    label: "Trung bình",
    dotClassName: "bg-amber-500",
    badgeClassName: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  high: {
    label: "Cao",
    dotClassName: "bg-rose-500",
    badgeClassName: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-400",
  },
}

export const STATUS_VIEW: Record<NavigationTaskStatus, {
  label: string
  pinClassName: string
  dotClassName: string
  badgeClassName: string
}> = {
  draft: {
    label: "Bản nháp",
    pinClassName: "fill-slate-400",
    dotClassName: "bg-slate-400",
    badgeClassName: "border-slate-400/30 bg-slate-400/10 text-slate-700 dark:text-slate-300",
  },
  submitting: {
    label: "Đang thêm",
    pinClassName: "fill-violet-500",
    dotClassName: "bg-violet-500",
    badgeClassName: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-400",
  },
  pending: {
    label: "Chờ xử lý",
    pinClassName: "fill-slate-500",
    dotClassName: "bg-slate-500",
    badgeClassName: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-400",
  },
  active: {
    label: "Đang thực hiện",
    pinClassName: "fill-blue-500",
    dotClassName: "bg-blue-500",
    badgeClassName: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400",
  },
  done: {
    label: "Hoàn thành",
    pinClassName: "fill-emerald-500",
    dotClassName: "bg-emerald-500",
    badgeClassName: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  error: {
    label: "Lỗi",
    pinClassName: "fill-red-500",
    dotClassName: "bg-red-500",
    badgeClassName: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
  },
  canceling: {
    label: "Đang hủy",
    pinClassName: "fill-orange-500",
    dotClassName: "bg-orange-500",
    badgeClassName: "border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-400",
  },
}

export const PRIORITY_ENTRIES = Object.entries(PRIORITY_VIEW) as [
  NavigationTaskPriority,
  typeof PRIORITY_VIEW[NavigationTaskPriority],
][]

export const STATUS_ENTRIES = Object.entries(STATUS_VIEW) as [
  NavigationTaskStatus,
  typeof STATUS_VIEW[NavigationTaskStatus],
][]
