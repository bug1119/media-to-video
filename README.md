# media-to-video

將指定目錄內的照片與影片依檔名排序，合併輸出為單一 MP4。照片預設顯示 2 秒，影片保留原長度與聲音，並可加入循環播放的 MP3 背景音樂。

## 需求

- Python 3.10+
- ffmpeg 與 ffprobe

macOS 可用 Homebrew 安裝：

```bash
brew install ffmpeg
```

## 使用方式

### 基本用法

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4"
```

### 加入背景音樂

背景音樂比成片短時會循環播放，超過成片長度時會自動截短。

保留影片原音，並混入音量 25% 的背景音樂：

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4" \
  --music "/path/to/music.mp3" \
  --audio-mode mix \
  --music-volume 0.25
```

只使用背景音樂，取代影片原音：

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4" \
  --music "/path/to/music.mp3" \
  --audio-mode music
```

忽略 `--music`，只保留影片原音：

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4" \
  --audio-mode original
```

## 實際範例

```bash
python3 media-to-video/media_to_video.py \
  "/Volumes/photo/picture/2026/202601" \
  --output "/Volumes/photo/picture/2026/202601.mp4" \
  --music "/path/to/music.mp3" \
  --photo-duration 2 \
  --audio-mode mix \
  --music-volume 0.25
```

## 參數

| 參數 | 預設值 | 說明 |
|---|---:|---|
| `directory` | 必填 | 照片與影片所在目錄 |
| `--output`, `-o` | `output.mp4` | 輸出 MP4 路徑 |
| `--music` | 無 | MP3 或 ffmpeg 可讀取的音訊檔 |
| `--photo-duration` | `2.0` | 每張照片顯示秒數 |
| `--resolution` | `1920x1080` | 輸出解析度，寬高需為偶數 |
| `--fps` | `30` | 輸出 frame rate |
| `--fit pad` | `pad` | 保留完整畫面，不足處補黑邊 |
| `--fit crop` | | 裁切畫面以填滿輸出尺寸 |
| `--audio-mode mix` | `mix` | 混合影片原音與背景音樂 |
| `--audio-mode music` | | 只使用背景音樂 |
| `--audio-mode original` | | 忽略背景音樂，只保留原音 |
| `--music-volume` | `0.25` | 背景音樂音量倍率 |

## 支援格式

照片：

- JPG / JPEG
- PNG
- WebP
- HEIC / HEIF，需 ffmpeg build 支援

影片：

- MP4
- MOV / M4V
- AVI
- MKV
- WebM

## 輸出行為

- 素材依檔名排序。
- 每個素材會先轉為一致的解析度、frame rate、H.264 視訊與 AAC stereo 音訊，再進行串接。
- 沒有音軌的影片與照片會加入靜音音軌，避免串接失敗。
- 預設使用黑邊保留直式照片與不同比例素材的完整畫面。
- 程式會在暫存目錄建立中間片段，完成或失敗後自動清除。

## 注意事項

- 大量高解析度照片或影片需要較長處理時間及暫存空間。
- 輸出檔若已存在會被覆寫。
- 程式只讀取指定目錄的第一層，不遞迴處理子目錄。
