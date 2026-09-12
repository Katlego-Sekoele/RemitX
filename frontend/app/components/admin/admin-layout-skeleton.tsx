import { Skeleton } from "~/components/ui/skeleton"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarRail,
  SidebarSeparator,
} from "~/components/ui/sidebar"

export function AdminLayoutSkeleton() {
  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <div className="flex h-12 items-center gap-2 px-2">
                <Skeleton className="size-6 shrink-0" />
                <div className="grid flex-1 gap-1 group-data-[collapsible=icon]:hidden">
                  <Skeleton className="h-3.5 w-20" />
                  <Skeleton className="h-3 w-16" />
                </div>
              </div>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>
              <Skeleton className="h-3 w-16" />
            </SidebarGroupLabel>
            <SidebarMenu>
              <SidebarMenuItem>
                <div className="flex h-8 items-center gap-2 px-2">
                  <Skeleton className="size-4 shrink-0" />
                  <Skeleton className="h-3.5 w-10 group-data-[collapsible=icon]:hidden" />
                  <Skeleton className="ml-auto size-3 group-data-[collapsible=icon]:hidden" />
                </div>
                <SidebarMenuSub>
                  <SidebarMenuSubItem>
                    <div className="flex h-7 items-center px-2 group-data-[collapsible=icon]:hidden">
                      <Skeleton className="h-3 w-14" />
                    </div>
                  </SidebarMenuSubItem>
                </SidebarMenuSub>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <div className="flex items-center justify-between gap-2 px-2 py-1 group-data-[collapsible=icon]:justify-center">
                <Skeleton className="h-3 w-10 group-data-[collapsible=icon]:hidden" />
                <Skeleton className="size-7 shrink-0" />
              </div>
            </SidebarMenuItem>
          </SidebarMenu>
          <SidebarSeparator />
          <SidebarMenu>
            <SidebarMenuItem>
              <div className="flex h-12 items-center gap-2 px-2">
                <Skeleton className="size-8 shrink-0 rounded-full" />
                <div className="grid flex-1 gap-1 group-data-[collapsible=icon]:hidden">
                  <Skeleton className="h-3.5 w-24" />
                  <Skeleton className="h-3 w-32" />
                </div>
              </div>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset>
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <Skeleton className="size-7 shrink-0" />
          <Skeleton className="hidden h-4 w-px md:block" />
          <div className="flex items-center gap-2">
            <Skeleton className="hidden h-3 w-12 md:block" />
            <Skeleton className="hidden size-3 md:block" />
            <Skeleton className="h-3 w-20" />
          </div>
        </header>
        <div
          className="flex flex-1 flex-col gap-4 p-4 md:p-6"
          role="status"
          aria-label="Loading staff portal"
        >
          <div className="flex flex-col gap-2">
            <Skeleton className="h-8 w-40" />
            <Skeleton className="h-4 w-full max-w-xl" />
          </div>
          <Skeleton className="h-36 w-full max-w-md" />
        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
