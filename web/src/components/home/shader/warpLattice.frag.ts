// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

export const WARP_LATTICE_FRAG = `#version 300 es
precision highp float;
uniform vec2 uResolution;
uniform float uOrder;
uniform vec3 uPaper;
uniform vec3 uThread;
uniform vec3 uThreadSoft;
uniform vec3 uKnots[8];
out vec4 fragColor;

void main() {
  vec2 uv = gl_FragCoord.xy / uResolution;
  float aspect = uResolution.x / uResolution.y;
  vec2 woven = uv;
  woven.x += 0.09 * sin(uv.y * 7.0 + uv.x * 3.0) + (1.0 - uOrder) * 0.08 * sin(uv.y * 17.0);
  woven.y += 0.12 * sin(uv.x * 5.0 - uv.y * 2.0);
  vec2 grid = woven * vec2(23.0, 15.0);
  vec2 distanceToLine = abs(fract(grid - 0.5) - 0.5) / fwidth(grid);
  float thread = 1.0 - smoothstep(0.0, 0.8, min(distanceToLine.x, distanceToLine.y));
  float lightPaper = step(0.5, uPaper.r);
  vec3 col = mix(uPaper, uThreadSoft, lightPaper * 0.05);
  col = mix(col, uThread, thread * mix(0.15, 0.11, lightPaper) * (0.3 + 0.7 * uOrder));
  for (int i = 0; i < 8; i++) {
    float d = length((uv - uKnots[i].xy) * vec2(aspect, 1.0));
    float halo = exp(-d * d * 2100.0) * 0.10;
    float knot = 1.0 - smoothstep(0.002, 0.006, d);
    col = mix(col, uThread, (halo + knot * 0.8) * uOrder);
  }
  fragColor = vec4(col, 1.0);
}
`
