# 天の川背景

`milky-way-source.png` は組み込み image_gen ツールで生成した原画です。
`milky-way.bmp` は内容を変えずにBMP形式へ変換した、ゲームが読み込む画像です。
実行時に2px単位へ縮小・拡大し、明るさを原画の約90%にして背景に描画します。
画像の生成・変換に使ったツールはゲームの実行には不要です。

## 生成プロンプト

Use case: stylized-concept. Asset type: background bitmap for an 800x600 classic pixel-art Space Invaders game. Primary request: a beautiful restrained Milky Way galaxy pixel-art backdrop, seen from within our galaxy as a diagonal luminous star band with a broad galactic core and dark dust lanes, crossing deep near-black navy space. Style: authentic low-resolution 16-bit pixel art, visible crisp square pixels, restrained dithering, no smooth photographic gradients. Composition: landscape 4:3, diffuse diagonal band from lower-left to upper-right, richer core slightly to the right of center, plenty of calm dark space, sparse tiny stars. Colors: muted indigo, dusty violet, slate blue and a subtle warm ivory core; low saturation and low brightness, suitable behind bright cyan, pink and green enemy sprites. Overall mood quiet and distant, no bright flares. Constraints: background only; no text, labels, UI, frame, foreground objects, spaceships, planets, characters, watermark. It must remain unobtrusive during gameplay.
