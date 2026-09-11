// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react'
import { usePerformanceMode } from '@/contexts/PerformanceModeContext'

export type ShaderUniforms = Record<string, number | readonly number[]>

export type ShaderSurfaceOptions = {
  fragment: string
  uniforms: () => ShaderUniforms
  animate: boolean
  maxDpr?: number
  fps?: 30 | 60
}

export type ShaderSurfaceState = 'webgl' | 'fallback' | 'idle'

const VERTEX_SHADER = `#version 300 es
layout(location = 0) in vec2 aPos;
void main() {
  gl_Position = vec4(aPos, 0.0, 1.0);
}
`

function compileShader(gl: WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)
  if (!shader) return null
  gl.shaderSource(shader, source)
  gl.compileShader(shader)
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader)
    gl.deleteShader(shader)
    if (import.meta.env.DEV) {
      console.warn('[useShaderSurface] shader compile failed:', info)
    }
    return null
  }
  return shader
}

function prefersReducedMotion() {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function useShaderSurface(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  options: ShaderSurfaceOptions,
): ShaderSurfaceState {
  const { isLite } = usePerformanceMode()
  const [state, setState] = useState<ShaderSurfaceState>('idle')
  const optionsRef = useRef(options)
  optionsRef.current = options

  const animateRef = useRef(options.animate)
  animateRef.current = options.animate

  const uniformsRef = useRef(options.uniforms)
  uniformsRef.current = options.uniforms

  const resetKey = `${isLite}|${options.animate}`

  const setUniforms = useCallback((gl: WebGL2RenderingContext, program: WebGLProgram) => {
    const values = uniformsRef.current()
    for (const [name, value] of Object.entries(values)) {
      const location = gl.getUniformLocation(program, name)
      if (!location) continue
      if (typeof value === 'number') {
        gl.uniform1f(location, value)
      } else if (value.length === 2) {
        gl.uniform2f(location, value[0], value[1])
      } else if (value.length === 3) {
        gl.uniform3f(location, value[0], value[1], value[2])
      } else if (value.length === 4) {
        gl.uniform4f(location, value[0], value[1], value[2], value[3])
      } else if (value.length === 24) {
        gl.uniform3fv(location, value as unknown as Float32List)
      } else {
        gl.uniform1fv(location, value as unknown as Float32List)
      }
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    if (isLite) {
      setState('fallback')
      return
    }

    const gl = canvas.getContext('webgl2', {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: 'low-power',
    })
    if (!gl) {
      setState('fallback')
      return
    }

    const onLost = (event: Event) => {
      event.preventDefault()
      setState('fallback')
    }
    canvas.addEventListener('webglcontextlost', onLost)

    const vs = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER)
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, optionsRef.current.fragment)
    if (!vs || !fs) {
      setState('fallback')
      return () => canvas.removeEventListener('webglcontextlost', onLost)
    }

    const program = gl.createProgram()
    if (!program) {
      setState('fallback')
      return () => canvas.removeEventListener('webglcontextlost', onLost)
    }
    gl.attachShader(program, vs)
    gl.attachShader(program, fs)
    gl.linkProgram(program)
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      if (import.meta.env.DEV) {
        console.warn('[useShaderSurface] program link failed:', gl.getProgramInfoLog(program))
      }
      setState('fallback')
      return () => canvas.removeEventListener('webglcontextlost', onLost)
    }

    const buffer = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(0)
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)

    gl.useProgram(program)

    let raf = 0
    let last = 0
    let visible = true
    const reduced = prefersReducedMotion()
    const shouldAnimate = animateRef.current && !reduced
    const maxDpr = optionsRef.current.maxDpr ?? 1.5
    const frameInterval = 1000 / (optionsRef.current.fps ?? 60)

    const resize = () => {
      const dpr = Math.min(globalThis.devicePixelRatio || 1, maxDpr)
      const width = Math.max(1, Math.floor(canvas.clientWidth * dpr))
      const height = Math.max(1, Math.floor(canvas.clientHeight * dpr))
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width
        canvas.height = height
      }
      gl.viewport(0, 0, width, height)
    }

    const draw = (time: number) => {
      resize()
      setUniforms(gl, program)
      gl.drawArrays(gl.TRIANGLES, 0, 3)
      last = time
    }

    const loop = (time: number) => {
      if (!visible) return
      if (time - last >= frameInterval) {
        draw(time)
      }
      raf = requestAnimationFrame(loop)
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        visible = entry?.isIntersecting ?? true
        if (visible && shouldAnimate && !raf) {
          last = performance.now() - frameInterval
          raf = requestAnimationFrame(loop)
        }
        if (!visible && raf) {
          cancelAnimationFrame(raf)
          raf = 0
        }
      },
      { threshold: 0.05 },
    )
    io.observe(canvas)

    const ro = new ResizeObserver(() => {
      resize()
      if (!shouldAnimate) draw(performance.now())
    })
    ro.observe(canvas)

    const onVisibility = () => {
      if (document.visibilityState !== 'visible') {
        if (raf) {
          cancelAnimationFrame(raf)
          raf = 0
        }
      } else if (shouldAnimate && visible && !raf) {
        last = performance.now() - frameInterval
        raf = requestAnimationFrame(loop)
      }
    }
    document.addEventListener('visibilitychange', onVisibility)

    if (shouldAnimate) {
      raf = requestAnimationFrame(loop)
    } else {
      draw(reduced ? 8 : 0)
    }

    const paletteObserver = new MutationObserver(() => {
      if (!shouldAnimate) draw(performance.now())
    })
    paletteObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-route-surface'] })

    setState('webgl')

    return () => {
      cancelAnimationFrame(raf)
      io.disconnect()
      ro.disconnect()
      paletteObserver.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      canvas.removeEventListener('webglcontextlost', onLost)
      gl.deleteBuffer(buffer)
      gl.deleteProgram(program)
      gl.deleteShader(vs)
      gl.deleteShader(fs)
    }
  }, [canvasRef, isLite, resetKey, setUniforms])

  return state
}
