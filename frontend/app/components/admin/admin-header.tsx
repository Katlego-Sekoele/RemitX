import { Link } from "react-router"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "~/components/ui/breadcrumb"
import { Separator } from "~/components/ui/separator"
import { SidebarTrigger } from "~/components/ui/sidebar"

type Crumb = {
  label: string
  href?: string
}

type AdminHeaderProps = {
  crumbs: Crumb[]
}

export function AdminHeader({ crumbs }: AdminHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator
        orientation="vertical"
        className="mr-2 data-vertical:h-4 data-vertical:self-auto"
      />
      <Breadcrumb>
        <BreadcrumbList>
          {crumbs.map((crumb, index) => {
            const isLast = index === crumbs.length - 1

            return (
              <span key={`${crumb.label}-${index}`} className="contents">
                {index > 0 ? (
                  <BreadcrumbSeparator className="hidden md:block" />
                ) : null}
                <BreadcrumbItem
                  className={index === 0 ? "hidden md:block" : ""}
                >
                  {isLast || !crumb.href ? (
                    <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                  ) : (
                    <BreadcrumbLink render={<Link to={crumb.href} />}>
                      {crumb.label}
                    </BreadcrumbLink>
                  )}
                </BreadcrumbItem>
              </span>
            )
          })}
        </BreadcrumbList>
      </Breadcrumb>
    </header>
  )
}
