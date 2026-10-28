import {
  Children,
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useMemo,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react"
import { mergeProps } from "@base-ui/react/merge-props"
import { useRender } from "@base-ui/react/use-render"
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  MeasuringStrategy,
  MouseSensor,
  TouchSensor,
  defaultDropAnimationSideEffects,
  useSensor,
  useSensors,
  type DragCancelEvent,
  type DragEndEvent,
  type DragStartEvent,
  type DraggableSyntheticListeners,
  type DropAnimation,
  type Modifiers,
  type UniqueIdentifier,
} from "@dnd-kit/core"
import {
  SortableContext,
  arrayMove,
  defaultAnimateLayoutChanges,
  rectSortingStrategy,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
  type AnimateLayoutChanges,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { createPortal } from "react-dom"

import { cn } from "cn"

/**
 * Drag-and-drop list from ReUI (`@reui/sortable`). Items reorder in memory;
 * the caller decides when that order is saved.
 */

const SortableItemContext = createContext<{
  listeners: DraggableSyntheticListeners | undefined
  isDragging?: boolean
  disabled?: boolean
}>({
  listeners: undefined,
  isDragging: false,
  disabled: false,
})

const IsOverlayContext = createContext(false)

const SortableInternalContext = createContext<{
  activeId: UniqueIdentifier | null
  modifiers?: Modifiers
}>({
  activeId: null,
  modifiers: undefined,
})

const animateLayoutChanges: AnimateLayoutChanges = (args) =>
  defaultAnimateLayoutChanges({ ...args, wasDragging: true })

const dropAnimationConfig: DropAnimation = {
  sideEffects: defaultDropAnimationSideEffects({
    styles: { active: { opacity: "0.4" } },
  }),
}

const subscribeToNothing = () => () => {}
const getIsMounted = () => true
const getIsMountedOnServer = () => false

const MOUSE_SENSOR_OPTIONS = { activationConstraint: { distance: 8 } }
const TOUCH_SENSOR_OPTIONS = {
  activationConstraint: { delay: 250, tolerance: 5 },
}
const KEYBOARD_SENSOR_OPTIONS = {
  coordinateGetter: sortableKeyboardCoordinates,
}
const MEASURING_CONFIG = {
  droppable: { strategy: MeasuringStrategy.Always },
}
const STRATEGY_MAP = {
  horizontal: rectSortingStrategy,
  grid: rectSortingStrategy,
  vertical: verticalListSortingStrategy,
} as const

type SortableChildProps = { value?: string; className?: string }

export interface SortableRootProps<T> extends Omit<
  useRender.ComponentProps<"div">,
  "onDragStart" | "onDragEnd" | "children"
> {
  value: T[]
  onValueChange: (value: T[]) => void
  getItemValue: (item: T) => string
  children: ReactNode
  strategy?: "horizontal" | "vertical" | "grid"
  onDragStart?: (event: DragStartEvent) => void
  onDragEnd?: (event: DragEndEvent) => void
  onDragCancel?: (event: DragCancelEvent) => void
  modifiers?: Modifiers
}

function Sortable<T>({
  value,
  onValueChange,
  getItemValue,
  className,
  render,
  strategy = "vertical",
  onDragStart,
  onDragEnd,
  onDragCancel,
  modifiers,
  children,
  ...props
}: SortableRootProps<T>) {
  const [activeId, setActiveId] = useState<UniqueIdentifier | null>(null)
  const mounted = useSyncExternalStore(
    subscribeToNothing,
    getIsMounted,
    getIsMountedOnServer
  )
  const sensors = useSensors(
    useSensor(MouseSensor, MOUSE_SENSOR_OPTIONS),
    useSensor(TouchSensor, TOUCH_SENSOR_OPTIONS),
    useSensor(KeyboardSensor, KEYBOARD_SENSOR_OPTIONS)
  )

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      setActiveId(event.active.id)
      onDragStart?.(event)
    },
    [onDragStart]
  )

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event
      setActiveId(null)
      onDragEnd?.(event)
      if (!over || active.id === over.id) return
      const activeIndex = value.findIndex(
        (item) => getItemValue(item) === active.id
      )
      const overIndex = value.findIndex(
        (item) => getItemValue(item) === over.id
      )
      if (activeIndex === -1 || overIndex === -1 || activeIndex === overIndex) {
        return
      }
      onValueChange(arrayMove(value, activeIndex, overIndex))
    },
    [value, getItemValue, onValueChange, onDragEnd]
  )

  const handleDragCancel = useCallback(
    (event: DragCancelEvent) => {
      setActiveId(null)
      onDragCancel?.(event)
    },
    [onDragCancel]
  )

  const itemIds = useMemo(
    () => value.map((item) => getItemValue(item)),
    [value, getItemValue]
  )

  const contextValue = useMemo(
    () => ({ activeId, modifiers }),
    [activeId, modifiers]
  )

  const overlayContent = useMemo(() => {
    if (!activeId) return null
    let result: ReactNode = null
    Children.forEach(children, (child) => {
      if (!isValidElement<SortableChildProps>(child)) return
      if (child.props.value !== activeId) return
      result = cloneElement(child as ReactElement<SortableChildProps>, {
        className: cn(child.props.className, "z-50"),
      })
    })
    return result
  }, [activeId, children])

  const sortableProps = {
    className: cn(activeId !== null && "cursor-grabbing!", className),
    "data-slot": "sortable",
    children,
  }

  return (
    <SortableInternalContext.Provider value={contextValue}>
      <DndContext
        sensors={sensors}
        modifiers={modifiers}
        measuring={MEASURING_CONFIG}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        <SortableContext
          items={itemIds}
          strategy={STRATEGY_MAP[strategy] ?? verticalListSortingStrategy}
        >
          {useRender({
            defaultTagName: "div",
            render,
            props: mergeProps<"div">(sortableProps, props),
          })}
          {mounted
            ? createPortal(
                <DragOverlay
                  dropAnimation={dropAnimationConfig}
                  modifiers={modifiers}
                  className={cn("z-50", activeId && "cursor-grabbing")}
                >
                  <IsOverlayContext.Provider value={true}>
                    {overlayContent}
                  </IsOverlayContext.Provider>
                </DragOverlay>,
                document.body
              )
            : null}
        </SortableContext>
      </DndContext>
    </SortableInternalContext.Provider>
  )
}

export interface SortableItemProps extends useRender.ComponentProps<"div"> {
  value: string
  disabled?: boolean
}

function SortableItem({
  value,
  className,
  render,
  disabled,
  ...props
}: SortableItemProps) {
  const isOverlay = useContext(IsOverlayContext)
  const {
    setNodeRef,
    transform,
    transition,
    attributes,
    listeners,
    isDragging: isSortableDragging,
  } = useSortable({
    id: value,
    disabled: disabled || isOverlay,
    animateLayoutChanges,
  })

  const style = {
    transition,
    transform: CSS.Transform.toString(transform),
  } as CSSProperties

  const dragging = isOverlay || isSortableDragging
  const defaultProps = isOverlay
    ? {
        "data-slot": "sortable-item",
        "data-value": value,
        "data-dragging": true,
        className: cn(className),
        children: props.children,
      }
    : {
        "data-slot": "sortable-item",
        "data-value": value,
        "data-dragging": isSortableDragging,
        "data-disabled": disabled,
        ref: setNodeRef,
        style,
        ...attributes,
        className: cn(
          dragging && "z-50 opacity-50",
          disabled && "opacity-50",
          className
        ),
        children: props.children,
      }

  return (
    <SortableItemContext.Provider
      value={
        isOverlay
          ? { listeners: undefined, isDragging: true, disabled: false }
          : { listeners, isDragging: isSortableDragging, disabled }
      }
    >
      {useRender({
        defaultTagName: "div",
        render,
        props: mergeProps<"div">(defaultProps, props),
      })}
    </SortableItemContext.Provider>
  )
}

export interface SortableItemHandleProps extends useRender.ComponentProps<"div"> {
  cursor?: boolean
}

function SortableItemHandle({
  className,
  render,
  cursor = true,
  ...props
}: SortableItemHandleProps) {
  const { listeners, isDragging, disabled } = useContext(SortableItemContext)

  const defaultProps = {
    className: cn(
      cursor && (isDragging ? "cursor-grabbing!" : "cursor-grab!"),
      className
    ),
    "data-slot": "sortable-item-handle",
    children: props.children,
    ...listeners,
  }

  return useRender({
    defaultTagName: "div",
    render,
    props: mergeProps<"div">(defaultProps, props),
  })
}

export { Sortable, SortableItem, SortableItemHandle }
