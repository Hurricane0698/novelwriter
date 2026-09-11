# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only
"""Build the landing title font from Google Fonts' NotoSerifSC[wght].ttf.

uv --no-config run --no-project --with fonttools --with brotli web/scripts/subset-display-font.py /path/to/NotoSerifSC.ttf
Source: https://github.com/google/fonts/tree/main/ofl/notoserifsc (SIL OFL 1.1)
"""
import re
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

web = Path(__file__).resolve().parents[1]
messages = (web / 'src/lib/uiMessagePacks/home.ts').read_text().split('export const homeEnMessages')[0]
titles = re.findall(r"'home\.[^']*\.title': [\"']([^\n]+?)[\"'],", messages)
text = ''.join(titles)
font = TTFont(sys.argv[1])
options = subset.Options()
options.flavor = 'woff2'
options.layout_features = []
subsetter = subset.Subsetter(options=options)
subsetter.populate(text=text)
subsetter.subset(font)
font = instantiateVariableFont(font, {'wght': 500}, inplace=True)
font.flavor = 'woff2'
output = web / 'public/fonts/novwr-display-zh.woff2'
font.save(output)
print(f'{len(set(text))} characters; {output.stat().st_size:,} bytes: {output}')
