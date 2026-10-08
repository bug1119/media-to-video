# media-to-video

將指定目錄內的照片與影片依檔名排序，合併輸出為單一 MP4。照片預設顯示 1.5 秒，影片保留原長度與聲音，並可加入循環播放的 MP3 背景音樂。程式會優先依影片解析度，自動選擇 4K、2K 或 1080p 輸出；只有照片時才依照片判斷。

## 需求

- Python 3.10+
- ffmpeg 與 ffprobe

macOS 可用 Homebrew 安裝：

```bash
brew install ffmpeg
```

## 使用方式

直接執行但不帶參數時，會顯示完整參數與使用範例：

```bash
./media-to-video/media_to_video.py
```

### 基本用法

單目錄模式未指定 `--output` 時，使用素材目錄名稱作為檔名，輸出到目前工作目錄。例如讀取 `/path/to/202601`，預設輸出 `202601.mp4`。

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4"
```

預設 `--resolution auto` 的選擇規則：目錄內有影片時，以所有影片作為判斷素材，照片不影響輸出解析度；無影片時，以所有照片判斷。

1. 所有素材的長邊與短邊都至少為 3840×2160，輸出 4K。
2. 否則，所有素材都至少為 2560×1440，輸出 2K/QHD。
3. 否則輸出 1920×1080；較小素材會被放大。

直式素材會交換長短邊判斷，例如 2160×3840 也視為 4K。採用判斷素材中最低解析度決定輸出，例如 4K 影片搭配低解析度照片仍輸出 4K；4K 與 1080p 影片混用則輸出 1080p。

也可停用自動判斷，手動指定輸出解析度：

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4" \
  --resolution 3840x2160
```

### 子目錄批次輸出

指定目錄內有第一層子目錄時，每個子目錄單獨製作一支影片，以子目錄名稱命名，預設放在指定的父目錄。例如：

```text
albums/
  trip-a/          → albums/trip-a.mp4
  trip-b/          → albums/trip-b.mp4
```

```bash
python3 media-to-video/media_to_video.py "/path/to/albums" \
  --photo-duration 3
```

`--photo-duration` 指定每張照片顯示幾秒（預設 1.5 秒，可使用小數）。批次模式的 `--output` 為輸出資料夾：

```bash
python3 media-to-video/media_to_video.py "/path/to/albums" \
  --output "/path/to/rendered" \
  --photo-duration 3 --workers 2 --threads 4
```

子目錄依名稱排序，逐一製作影片；每支影片內的素材仍並行轉檔。所有子目錄套用相同參數，但自動解析度各自判斷。沒有支援素材的子目錄會跳過；父目錄中的素材不參與批次輸出，也不遞迴讀取更深層目錄。指定的輸出資料夾不會當作輸入子目錄。

每支影片完成後顯示照片數、影片數與耗時，最後顯示整批合併數量與執行時間。沒有子目錄時，維持原本單一影片的輸出方式。

### 多核心並行轉檔

預設同時處理 2 個檔案，每個工作的 H.264 編碼使用 4 個執行緒。可依 CPU 核心數與記憶體調整：

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4" \
  --workers 2 --threads 4
```

兩個參數都必須是正整數；`--workers 1` 可改為逐一轉檔。並行完成順序不影響成片的檔名排序。`--threads` 控制視訊編碼執行緒數，ffmpeg 的解碼與濾鏡仍可能使用額外執行緒。

### 加入背景音樂

背景音樂比成片短時會循環播放，超過成片長度時會自動截短。

`--music` 也可以指定音樂資料夾，程式會從第一層音訊檔中隨機選一首，並顯示選用的檔案路徑。批次模式下每支影片各自抽選，可能選到相同曲目：

```bash
python3 media-to-video/media_to_video.py "/path/to/albums" \
  --music "$HOME/Downloads/YouTube-Audio-Library" \
  --audio-mode mix --music-volume 0.25
```

資料夾支援 MP3、WAV、FLAC、M4A、AAC、OGG、Opus、AIFF/AIF、WMA（需 ffmpeg 支援解碼）。非音訊檔及更深層子目錄會略過；沒有支援音訊檔時會顯示錯誤。若音樂資料夾位於素材父目錄內，不會將它當作影片輸入子目錄。`--audio-mode original` 會忽略音樂設定，不抽選或驗證音樂。

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

### 執行 log

每次執行會同步將進度寫入 UTF-8 log，預設與輸出影片放在同一個資料夾，以素材目錄名稱命名。例如輸出 `/path/to/rendered/202601.mp4`，log 為 `/path/to/rendered/202601.log`。批次模式將所有子目錄的處理資訊記錄在輸出資料夾內同一個 `<父目錄名稱>.log`。紀錄包含時間戳記、參數、影片排除原因、選用音樂、ffmpeg 指令與錯誤、完成統計及執行時間；再次執行時追加到同一檔案。

可使用 `--log-file` 指定其他路徑：

```bash
python3 media-to-video/media_to_video.py "/path/to/202601" \
  --log-file "/path/to/logs/202601.log"
```

說明訊息與建立 log 前的參數解析錯誤只顯示於終端機。

| 參數 | 預設值 | 說明 |
|---|---:|---|
| `directory` | 必填 | 照片與影片所在目錄 |
| `--log-file` | 輸出影片資料夾內的 `<素材目錄名稱>.log` | 執行紀錄，包含時間戳記；同名檔案追加 |
| `--output`, `-o` | 單目錄：`<素材目錄名稱>.mp4`；批次：指定的父目錄 | 單目錄時為 MP4 路徑，預設放在目前工作目錄；批次時為輸出資料夾 |
| `--music` | 無 | 音訊檔，或每支影片隨機選一首的音樂資料夾 |
| `--photo-duration` | `1.5` | 每張照片顯示秒數 |
| `--resolution` | `auto` | 優先依影片選 4K/2K/1080p，無影片時依照片；或手動指定偶數尺寸 |
| `--fps` | `30` | 輸出 frame rate |
| `--workers` | `2` | 同時轉檔的檔案數（正整數） |
| `--threads` | `4` | 每個工作的 H.264 編碼執行緒數（正整數） |
| `--fit pad` | `pad` | 保留完整畫面，不足處補黑邊 |
| `--fit crop` | | 裁切畫面以填滿輸出尺寸 |
| `--audio-mode mix` | `mix` | 混合影片原音與背景音樂 |
| `--audio-mode music` | | 只使用背景音樂 |
| `--audio-mode original` | | 忽略背景音樂，只保留原音 |
| `--music-volume` | `0.5` | 背景音樂音量倍率 |

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

### 影片排除條件

每個素材目錄（批次模式下為各子目錄）獨立套用以下規則：

- 單一影片大於 **200 MB（200,000,000 bytes）** 時排除，剛好 200 MB 仍保留。
- 影片檔名以 **`video`** 開頭時排除，不分大小寫。
- 目錄內影片超過 **10 部** 時，排除該目錄全部影片，只合併照片；剛好 10 部仍依前兩項規則篩選。影片數在大小及檔名篩選前計算，不包含本次輸出檔。

程式會顯示每支影片的排除原因。解析度判斷及完成數量統計只使用實際保留的素材。若篩選後沒有素材，單目錄模式回報錯誤，批次模式跳過該子目錄。

- 素材依檔名排序。
- 自動解析度以所有影片中最低的長邊與短邊決定；無影片時才依所有照片判斷。
- 每個素材會先轉為一致的解析度、frame rate、H.264 視訊與 AAC stereo 音訊，再進行串接。
- 沒有音軌的影片與照片會加入靜音音軌，避免串接失敗。
- 預設使用黑邊保留直式照片與不同比例素材的完整畫面。
- 程式會在暫存目錄建立中間片段，完成或失敗後自動清除。
- 成功完成後顯示實際合併的照片數、影片數、素材總數及總執行時間（秒），包含解析度判斷、轉檔、串接與背景音樂處理。

## 注意事項

- 大量高解析度照片或影片需要較長處理時間及暫存空間。
- 輸出檔若已存在會被覆寫。
- 有子目錄時，每個第一層子目錄分別輸出影片，只讀取該子目錄直接包含的素材，不再向下遞迴。
