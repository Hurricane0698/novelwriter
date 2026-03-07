import * as React from "react"
import { cn } from "@/lib/utils"


// RE-IMPLEMENTING WITH CONTEXT for robustness
interface TabsContextType {
    value: string;
    onValueChange: (value: string) => void;
}
const TabsContext = React.createContext<TabsContextType | null>(null);

const TabsWithContext = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & { defaultValue?: string; value?: string; onValueChange?: (value: string) => void }
>(({ className, defaultValue, value, onValueChange, children, ...props }, ref) => {
    const [localValue, setLocalValue] = React.useState(defaultValue || "")

    const currentValue = value !== undefined ? value : localValue
    const handleValueChange = (newValue: string) => {
        if (value === undefined) setLocalValue(newValue)
        onValueChange?.(newValue)
    }

    return (
        <TabsContext.Provider value={{ value: currentValue, onValueChange: handleValueChange }}>
            <div ref={ref} className={cn("", className)} {...props}>
                {children}
            </div>
        </TabsContext.Provider>
    )
})
TabsWithContext.displayName = "Tabs"

const TabsListWithContext = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
    <div
        ref={ref}
        className={cn(
            "inline-flex h-10 items-center justify-center rounded-md bg-muted p-1 text-muted-foreground",
            className
        )}
        {...props}
    />
))
TabsListWithContext.displayName = "TabsList"

const TabsTriggerWithContext = React.forwardRef<
    HTMLButtonElement,
    React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }
>(({ className, value, ...props }, ref) => {
    const context = React.useContext(TabsContext)
    if (!context) throw new Error("TabsTrigger must be used within Tabs")

    const isSelected = context.value === value

    return (
        <button
            ref={ref}
            type="button"
            onClick={() => context.onValueChange(value)}
            className={cn(
                "inline-flex items-center justify-center whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
                isSelected
                    ? "bg-background text-foreground shadow-sm"
                    : "hover:bg-background/50 hover:text-foreground",
                className
            )}
            {...props}
        />
    )
})
TabsTriggerWithContext.displayName = "TabsTrigger"

const TabsContentWithContext = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & { value: string }
>(({ className, value, children, ...props }, ref) => {
    const context = React.useContext(TabsContext)
    if (!context) throw new Error("TabsContent must be used within Tabs")

    if (context.value !== value) return null

    return (
        <div
            ref={ref}
            className={cn(
                "mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 animate-in fade-in-50 zoom-in-95 data-[state=inactive]:animate-out data-[state=inactive]:fade-out-0 data-[state=inactive]:zoom-out-95",
                className
            )}
            {...props}
        >
            {children}
        </div>
    )
})
TabsContentWithContext.displayName = "TabsContent"

export { TabsWithContext as Tabs, TabsListWithContext as TabsList, TabsTriggerWithContext as TabsTrigger, TabsContentWithContext as TabsContent }
