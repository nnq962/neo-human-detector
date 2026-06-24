import { useEffect } from "react"
import { useForm, Controller } from "react-hook-form"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { camerasApi, type Camera } from "@/api/cameras.api"
import { mediamtxApi } from "@/api/mediamtx.api"
import { useInvalidateCameras } from "@/hooks/use-cameras"

const schema = z.object({
  name: z.string().min(1, "Bắt buộc"),
  enabled: z.boolean(),
})

type FormValues = z.infer<typeof schema>

interface Props {
  camera: Camera
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EditCameraDialog({ camera, open, onOpenChange }: Props) {
  const invalidateCameras = useInvalidateCameras()

  const { register, handleSubmit, control, reset, formState: { errors, isSubmitting } } =
    useForm<FormValues>({ resolver: zodResolver(schema) })

  useEffect(() => {
    if (open) reset({ name: camera.name, enabled: camera.enabled })
  }, [open, camera, reset])

  async function onSubmit(values: FormValues) {
    try {
      if (values.enabled) {
        const check = await mediamtxApi.checkCamera(camera.stream.source)
        if (!check.ready) {
          toast.error("Không kết nối được đến camera. Không thể bật camera này.")
          return
        }
      }

      await camerasApi.update(camera.id, {
        name: values.name,
        enabled: values.enabled,
      })
      toast.success("Đã cập nhật camera")
      invalidateCameras()
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Cập nhật thất bại")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Sửa camera</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">Tên</label>
            <Input {...register("name")} />
            {errors.name && (
              <p className="text-xs text-destructive">{errors.name.message}</p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium">Trạng thái</label>
            <Controller
              name="enabled"
              control={control}
              render={({ field }) => (
                <Select
                  value={field.value ? "true" : "false"}
                  onValueChange={(v) => field.onChange(v === "true")}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent position="popper">
                    <SelectItem value="true">Enabled</SelectItem>
                    <SelectItem value="false">Disabled</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          </div>

          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Đang xác nhận kết nối..." : "Lưu"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
