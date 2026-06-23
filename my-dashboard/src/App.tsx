import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"

function App() {
  return (
    <TooltipProvider>
      <div className="flex min-h-screen items-center justify-center">
        <Button>Hello AI Dashboard</Button>
      </div>

      <Toaster />
    </TooltipProvider>
  )
}

export default App