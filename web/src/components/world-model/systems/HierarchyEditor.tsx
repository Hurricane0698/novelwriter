import { useState } from 'react'
import { cn } from '@/lib/utils'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { LABELS } from '@/constants/labels'
import type { Visibility } from '@/types/api'

interface HierarchyNode {
  id: string
  label: string
  entity_id: number | null
  visibility: Visibility
  children: HierarchyNode[]
}

interface HierarchyData {
  nodes: HierarchyNode[]
}

function NodeRow({ node, depth, onUpdate, onDelete, onAddChild, onVisibilityChange }: {
  node: HierarchyNode
  depth: number
  onUpdate: (id: string, label: string) => void
  onDelete: (id: string) => void
  onAddChild: (parentId: string) => void
  onVisibilityChange: (id: string, v: Visibility) => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [hovered, setHovered] = useState(false)
  const children = node.children ?? []
  const hasChildren = children.length > 0

  return (
    <>
      <div
        className="flex items-center gap-1 py-1 rounded-lg group transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <button
          className={cn('w-4 h-4 text-xs text-muted-foreground shrink-0', !hasChildren && 'invisible')}
          onClick={() => setCollapsed(!collapsed)}
        >{collapsed ? '▶' : '▼'}</button>
        <VisibilityDot visibility={node.visibility ?? 'active'} onChange={v => onVisibilityChange(node.id, v)} />
        <InlineEdit value={node.label} onSave={v => onUpdate(node.id, v)} className="text-sm flex-1" placeholder={LABELS.PH_NODE_NAME} />
        {hovered && (
          <>
            <button
              className="text-muted-foreground hover:text-foreground text-xs px-1"
              onClick={() => onAddChild(node.id)}
            >+</button>
            <button
              className="text-muted-foreground hover:text-[hsl(var(--color-danger))] text-xs px-1"
              onClick={() => onDelete(node.id)}
            >×</button>
          </>
        )}
      </div>
      {!collapsed && children.map(child => (
        <NodeRow key={child.id} node={child} depth={depth + 1} onUpdate={onUpdate} onDelete={onDelete} onAddChild={onAddChild} onVisibilityChange={onVisibilityChange} />
      ))}
    </>
  )
}

function updateNodeLabel(nodes: HierarchyNode[], id: string, label: string): HierarchyNode[] {
  return nodes.map(n => n.id === id
    ? { ...n, label }
    : { ...n, children: updateNodeLabel(n.children ?? [], id, label) }
  )
}

function updateNodeVisibility(nodes: HierarchyNode[], id: string, visibility: Visibility): HierarchyNode[] {
  return nodes.map(n => n.id === id
    ? { ...n, visibility }
    : { ...n, children: updateNodeVisibility(n.children ?? [], id, visibility) }
  )
}

function deleteNode(nodes: HierarchyNode[], id: string): HierarchyNode[] {
  return nodes.filter(n => n.id !== id).map(n => ({ ...n, children: deleteNode(n.children ?? [], id) }))
}

function addChild(nodes: HierarchyNode[], parentId: string, child: HierarchyNode): HierarchyNode[] {
  return nodes.map(n => n.id === parentId
    ? { ...n, children: [...(n.children ?? []), child] }
    : { ...n, children: addChild(n.children ?? [], parentId, child) }
  )
}

let _nodeCounter = 0
const newId = () => `node_${Date.now()}_${++_nodeCounter}`

export function HierarchyEditor({ data, onUpdate }: {
  data: HierarchyData
  onUpdate: (data: HierarchyData) => void
}) {
  const nodes = data.nodes ?? []

  return (
    <div>
      {nodes.map(node => (
        <NodeRow
          key={node.id}
          node={node}
          depth={0}
          onUpdate={(id, label) => onUpdate({ nodes: updateNodeLabel(nodes, id, label) })}
          onDelete={id => onUpdate({ nodes: deleteNode(nodes, id) })}
          onAddChild={parentId => onUpdate({ nodes: addChild(nodes, parentId, { id: newId(), label: '', entity_id: null, visibility: 'active', children: [] }) })}
          onVisibilityChange={(id, v) => onUpdate({ nodes: updateNodeVisibility(nodes, id, v) })}
        />
      ))}
      <button
        className="text-sm text-muted-foreground hover:text-foreground px-2 py-1 mt-1"
        onClick={() => onUpdate({ nodes: [...nodes, { id: newId(), label: '', entity_id: null, visibility: 'active', children: [] }] })}
      >{LABELS.SYSTEM_ADD_ROOT}</button>
    </div>
  )
}
