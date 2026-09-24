"use client"

import * as React from "react"
import { cn } from "@/lib/utils"

function ScrollArea({ className, children, ...props }: any) {
  return (
    <div
      data-slot="scroll-area"
      className={cn("relative overflow-auto", className)}
      {...props}
    >
      {children}
    </div>
  )
}

function ScrollBar() {
  return null
}

export { ScrollArea, ScrollBar }
