// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

export const INK_DITHER_FRAG = `#version 300 es
precision highp float;

uniform vec2 uResolution;
uniform vec3 uFrame;
uniform vec3 uThreadSoft;

out vec4 fragColor;

// 4x4 Bayer matrix ordered dither.
float bayer4(vec2 p) {
  int x = int(mod(p.x, 4.0));
  int y = int(mod(p.y, 4.0));
  int index = y * 4 + x;
  float m[16];
  m[0]=0.0;  m[1]=8.0;  m[2]=2.0;  m[3]=10.0;
  m[4]=12.0; m[5]=4.0;  m[6]=14.0; m[7]=6.0;
  m[8]=3.0;  m[9]=11.0; m[10]=1.0; m[11]=9.0;
  m[12]=15.0;m[13]=7.0; m[14]=13.0;m[15]=5.0;
  for (int i = 0; i < 16; i++) {
    if (i == index) return (m[i] + 0.5) / 16.0;
  }
  return 0.5;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uResolution;
  float diagonal = clamp(uv.x * 0.55 + (1.0 - uv.y) * 0.45, 0.0, 1.0);
  float threshold = bayer4(gl_FragCoord.xy);
  float ink = step(threshold, diagonal * 0.35);
  vec3 col = mix(uFrame, uThreadSoft * 0.35, ink * 0.55);
  fragColor = vec4(col, 1.0);
}
`
