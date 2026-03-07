// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Plus, ShieldCheck } from 'lucide-react'
import { EmptyState } from '@/components/library/EmptyState'
import { WorkCard } from '@/components/library/WorkCard'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { GlassCard } from '@/components/GlassCard'
import { Checkbox } from '@/components/ui/checkbox'
import { api } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import { novelKeys } from '@/hooks/novel/keys'
import { clearWorldOnboardingDismissed } from '@/lib/worldOnboardingStorage'
import { readUploadConsent, UPLOAD_CONSENT_VERSION, writeUploadConsent } from '@/lib/uploadConsent'

export function LibraryPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const { user } = useAuth()
  const consentScope = user?.id ?? 'anonymous'
  const [hasConfirmedRights, setHasConfirmedRights] = useState(false)

  useEffect(() => {
    setHasConfirmedRights(readUploadConsent(consentScope))
  }, [consentScope])

  const { data: novels = [], isLoading: loading, error } = useQuery({
    queryKey: novelKeys.all,
    queryFn: () => api.listNovels(),
    staleTime: 30_000,
  })

  const deleteNovel = useMutation({
    mutationFn: (vars: { id: number, created_at?: string | null }) => api.deleteNovel(vars.id),
    onSuccess: (_data, vars) => {
      clearWorldOnboardingDismissed(vars.id, vars.created_at)
      queryClient.invalidateQueries({ queryKey: novelKeys.all })
    },
  })

  function handleDelete(id: number) {
    if (!window.confirm('确定要删除这部作品吗？此操作不可撤销。')) return
    const novel = novels.find((n) => n.id === id)
    deleteNovel.mutate({ id, created_at: novel?.created_at })
  }

  function handleCreate() {
    if (!hasConfirmedRights) return
    fileInputRef.current?.click()
  }

  function handleConsentChange(nextChecked: boolean) {
    setHasConfirmedRights(nextChecked)
    writeUploadConsent(consentScope, nextChecked)
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    if (!hasConfirmedRights) {
      alert('请先确认你对上传文本拥有必要权利。')
      e.target.value = ''
      return
    }
    const title = file.name.replace(/\.txt$/i, '')
    try {
      const result = await api.uploadNovel(file, title, '', UPLOAD_CONSENT_VERSION)
      queryClient.invalidateQueries({ queryKey: novelKeys.all })
      navigate(`/novel/${result.novel_id}`)
    } catch (err) {
      alert(err instanceof Error ? err.message : '上传失败')
    }
    e.target.value = ''
  }

  const createButton = (
    <NwButton
      data-testid="library-create-novel"
      onClick={handleCreate}
      disabled={!hasConfirmedRights}
      variant="accent"
      className="rounded-full px-6 py-2.5 text-sm font-semibold shadow-[0_0_24px_hsl(var(--accent)/0.35)]"
    >
      <Plus size={18} />
      新建作品
    </NwButton>
  )

  const legalLinks = (
    <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-muted-foreground">
      <Link to="/terms" className="transition-colors hover:text-foreground">查看用户规则</Link>
      <Link to="/privacy" className="transition-colors hover:text-foreground">查看隐私说明</Link>
      <Link to="/copyright" className="transition-colors hover:text-foreground">查看版权投诉说明</Link>
    </div>
  )

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="overflow-hidden">
      <input
        ref={fileInputRef}
        data-testid="library-file-input"
        type="file"
        accept=".txt"
        className="hidden"
        onChange={handleFileSelected}
      />
      <div className="flex flex-col flex-1 px-12 py-10 gap-8 overflow-auto">
        {/* Header */}
        <div className="flex items-center justify-between gap-6">
          <div className="flex flex-col gap-1">
            <h1 className="m-0 font-mono text-2xl font-bold text-foreground">
              我的作品库
            </h1>
            <p className="m-0 text-sm text-muted-foreground">
              管理你的所有小说作品
            </p>
          </div>
          {createButton}
        </div>

        {!hasConfirmedRights ? (
          <GlassCard className="relative overflow-hidden px-5 py-5 md:px-6 md:py-6">
            <div className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-accent/70 to-transparent" />
            <div className="flex flex-col gap-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex gap-3.5">
                  <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-accent/10 text-accent ring-1 ring-accent/20">
                    <ShieldCheck size={18} />
                  </div>
                  <div className="flex flex-col gap-2.5">
                    <h2 className="font-mono text-lg font-semibold text-foreground">上传前先确认权利边界</h2>
                    <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
                      请仅上传原创、已获授权或属于公共领域的文本内容。为降低版权风险，上传前需要你确认相关使用权利。
                    </p>
                    {legalLinks}
                  </div>
                </div>

                <label className="flex w-full max-w-xl items-start gap-3 rounded-2xl border border-[var(--nw-glass-border)] bg-white/5 px-4 py-3.5 text-sm leading-6 text-foreground/90 lg:ml-4">
                  <Checkbox checked={hasConfirmedRights} onCheckedChange={handleConsentChange} className="mt-1" />
                  <span>
                    我确认我对上传或输入的文本拥有合法、必要的使用权利，不会上传未经授权的受版权保护内容。
                  </span>
                </label>
              </div>

              <p className="text-xs leading-5 text-muted-foreground">
                勾选后会记住当前设备，下次进入作品库时自动生效。你仍可随时查看相关页面了解详细规则。
              </p>
            </div>
          </GlassCard>
        ) : (
          <GlassCard variant="control" className="flex flex-col gap-4 px-5 py-4 md:flex-row md:items-center md:justify-between md:px-6">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-[hsl(var(--color-status-confirmed)/0.14)] text-[hsl(var(--color-status-confirmed))] ring-1 ring-[hsl(var(--color-status-confirmed)/0.18)]">
                <CheckCircle2 size={18} />
              </div>
              <div className="flex flex-col gap-1">
                <div className="font-medium text-foreground">已确认上传权利边界</div>
                <p className="text-sm leading-6 text-muted-foreground">
                  当前设备已记住你的确认状态。上传前仍请确保文本属于原创、授权或公共领域内容。
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {legalLinks}
              <button
                type="button"
                onClick={() => handleConsentChange(false)}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              >
                重新确认
              </button>
            </div>
          </GlassCard>
        )}

        {/* Loading */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {[0, 1, 2, 3].map((i) => (
              <GlassCard
                key={i}
                className="h-40 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="text-sm text-[hsl(var(--color-warning))]">
            加载失败: {error instanceof Error ? error.message : '未知错误'}
          </p>
        )}

        {/* Empty */}
        {!loading && !error && novels.length === 0 && (
          <EmptyState onCreate={handleCreate} disabled={!hasConfirmedRights} />
        )}

        {/* Card Grid */}
        {!loading && !error && novels.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {novels.map((novel) => (
              <WorkCard key={novel.id} novel={novel} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}
