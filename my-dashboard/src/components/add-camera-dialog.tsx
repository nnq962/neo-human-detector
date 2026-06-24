import { useForm } from "react-hook-form"
import { z } from "zod"
import { zodResolver } from "@hookform/resolvers/zod"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { camerasApi } from "@/api/cameras.api"
import { mediamtxApi } from "@/api/mediamtx.api"
import { useInvalidateCameras } from "@/hooks/use-cameras"

const schema = z.object({
  name: z.string().min(1, "Bắt buộc"),
  source: z
    .string()
    .min(1, "Bắt buộc")
    .regex(/^rtsp:\/\/.+\..+/, "URL không hợp lệ, phải có dạng rtsp://..."),
})

type FormValues = z.infer<typeof schema>

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AddCameraDialog({ open, onOpenChange }: Props) {
  const invalidateCameras = useInvalidateCameras()

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } =
    useForm<FormValues>({ resolver: zodResolver(schema) })

  async function onSubmit(values: FormValues) {
    try {
      const check = await mediamtxApi.checkCamera(values.source)
      if (!check.ready) {
        toast.error("Không kết nối được đến camera. Kiểm tra lại RTSP URL.")
        return
      }

      const response = await camerasApi.create({
        name: values.name,
        stream: { source: values.source, protocol: "tcp", on_demand: true },
        enabled: true,
        zones: [],
      })
      toast.success(response.message)
      invalidateCameras()
      reset()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Thêm camera thất bại")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Thêm camera</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">Tên camera</label>
            <Input placeholder="VD: Phòng họp" {...register("name")} />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">RTSP URL</label>
            <Input placeholder="rtsp://user:pass@192.168.0.x:554/..." {...register("source")} />
            {errors.source && (
              <p className="text-xs text-destructive">{errors.source.message}</p>
            )}
          </div>

          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Đang kiểm tra kết nối..." : "Thêm"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
