// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

type NarrativeActProps = {
  title: string
  description: string
}

export function NarrativeAct({ title, description }: NarrativeActProps) {
  return (
    <div className="lp-narrative-act">
      <h3 className="lp-h3">{title}</h3>
      <p className="lp-body mt-4">{description}</p>
    </div>
  )
}
