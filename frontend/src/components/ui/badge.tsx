import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "group/badge inline-flex h-6 w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-lg border-2 px-2 py-0.5 text-xs font-bold whitespace-nowrap transition-[background-color,color,border-color] duration-100 focus-visible:ring-[3px] focus-visible:ring-ring/50 has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 aria-invalid:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 [&>svg]:pointer-events-none [&>svg]:size-3!",
  {
    variants: {
      variant: {
        default:
          "border-[#4a8a00] bg-[#58a700] text-white [a]:hover:bg-[#61bd00]",
        secondary:
          "border-[#c4c4c4] bg-[#eeeeee] text-[#4b4b4b] [a]:hover:bg-[#f5f5f5] dark:border-[#3f4650] dark:bg-[#59616d] dark:text-white dark:[a]:hover:bg-[#66707d]",
        destructive:
          "border-[#d33131] bg-[#ff4b4b] text-white focus-visible:ring-destructive/30 [a]:hover:bg-[#ff5c5c]",
        outline:
          "border-border bg-background text-foreground [a]:hover:bg-muted",
        ghost:
          "border-transparent bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground dark:hover:bg-muted/50",
        link:
          "border-transparent bg-transparent text-primary underline-offset-4 hover:underline",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span"

  return (
    <Comp
      data-slot="badge"
      data-variant={variant}
      className={cn(badgeVariants({ variant }), className)}
      {...props}
    />
  )
}

export { Badge }
