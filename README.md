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

### 日期目錄按月份合併

使用 `--date-group` 選擇日期目錄分組方式：

| 值 | 行為 | 輸出名稱範例 |
|---|---|---|
| `month`（預設） | 同月份照片合併 | `202601.mp4` |
| `week` | 同 ISO 週照片合併，週一至週日，可跨月／跨年 | `2026-W04.mp4` |
| `none` | 不合併日期目錄，各目錄獨立處理照片與符合條件的影片 | `20260121.mp4` |

```bash
python3 media-to-video/media_to_video.py "/path/to/picture" --date-group week
python3 media-to-video/media_to_video.py "/path/to/picture" --date-group none
```

直接指定日期目錄時，`week` 會合併同層同週的照片；`none` 只處理指定目錄。週次及年份依 ISO 週曆判斷，例如 `20251229` 與 `20260101` 都屬於 `2026-W01`。

按月分組只看目錄開頭的有效 `YYYYMM`（也支援 `YYYY-MM`），後面的日期或其他文字不影響月份。例如 `2025021828`、`20250218`、`202502` 都歸入 `202502`。按週分組使用前 8 碼有效日期 `YYYYMMDD`，尾端可接額外數字，例如 `2025021828` 以 `2025-02-18` 判斷週次；也支援完整的 `YYYY-MM-DD`。指定其中一個日期目錄時，會讀取同一父目錄下、同月份所有日期目錄的照片，依日期再依檔名排序，合併為 `YYYYMM.mp4`（預設放在目前工作目錄）：

```bash
python3 media-to-video/media_to_video.py "/path/to/picture/20260101"
# 合併同層 2026 年 1 月的日期目錄照片，輸出 202601.mp4 與 202601.log
```

指定父目錄時，日期子目錄會自動按月份分組，每月一支影片，預設輸出至父目錄；`--output` 可指定輸出資料夾：

```bash
python3 media-to-video/media_to_video.py "/path/to/picture" \
  --output "/path/to/rendered"
# 20260101、20260115 → rendered/202601.mp4
# 20260201、2026-02-15 → rendered/202602.mp4
```

月份影片只合併照片，忽略日期目錄內影片，不遞迴讀取更深層子目錄。HEIC/HEIF 等仍先轉 JPG，照片顯示秒數、音樂及解析度設定照常套用。非日期子目錄維持原本各自輸出影片的行為；按月只驗證年月，按週則需有效日期。月份輸出影片已存在時跳過該月份。

### 多核心並行轉檔

預設同時處理 2 個檔案，每個工作的 H.264 編碼使用 4 個執行緒。可依 CPU 核心數與記憶體調整：

```bash
python3 media-to-video/media_to_video.py "/path/to/media" \
  --output "/path/to/output.mp4" \
  --workers 2 --threads 4
```

兩個參數都必須是正整數；`--workers 1` 可改為逐一轉檔。並行完成順序不影響成片的檔名排序。`--threads` 控制視訊編碼執行緒數，ffmpeg 的解碼與濾鏡仍可能使用額外執行緒。

### 加入背景音樂

指定單一音樂檔時，比成片短就循環播放。指定音樂資料夾時，曲目隨機接續播放直到影片結束；整份曲單播完才重新洗牌，避免連續同一首（只有一首時仍循環）。最後一首超過成片長度會自動截短，不做曲間交叉淡化。

未指定 `--music` 時，預設從 `/Volumes/photo/picture/YouTube-Audio-Library/` 隨機選曲。該目錄不存在時，略過背景音樂並保留影片原音，略過原因會記錄於終端機與 log。可用 `--music` 指定其他檔案或資料夾，或使用 `--audio-mode original` 停用背景音樂。

`--music` 也可以指定音樂資料夾，程式會從第一層音訊檔中隨機選擇起始曲並接續換曲，顯示每首曲目及其起始秒數。批次模式下每支影片各自產生隨機曲單：

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
| `--date-group` | `month` | 日期目錄按月、按週或不合併：`month` / `week` / `none` |
| `--log-file` | 輸出影片資料夾內的 `<素材目錄名稱>.log` | 執行紀錄，包含時間戳記；同名檔案追加 |
| `--output`, `-o` | 單目錄：`<素材目錄名稱>.mp4`；批次：指定的父目錄 | 單目錄時為 MP4 路徑，預設放在目前工作目錄；批次時為輸出資料夾 |
| `--music` | `/Volumes/photo/picture/YouTube-Audio-Library/` | 音訊檔或隨機選曲資料夾；預設目錄不存在時略過 |
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
- HEIC / HEIF

PNG、WebP、HEIC / HEIF 會先轉成暫存 JPG 再合併；JPG/JPEG 直接使用。原始圖片不會被覆寫，暫存 JPG 會隨中間片段清除。macOS 的 HEIC / HEIF 使用內建 `sips` 轉換；其他系統需 ffmpeg 支援 HEIC / HEIF 解碼。轉換進度會記錄於終端機與 log。

影片：

- MP4
- MOV / M4V
- AVI
- MKV
- WebM

## 輸出行為

### 壞圖與空檔案

大小為 0 bytes 的照片或影片會跳過。圖片若轉 JPG 失敗、無法取得寬高或影片轉檔失敗，會記錄原始檔名與原因並跳過，不中斷整批。手動指定解析度時仍會檢查圖片尺寸。原始檔案保留；完成統計只包含成功合併的素材，全部素材無效時不產生影片並繼續下一個目錄。

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

- ffmpeg 使用 `-nostdin` 並隔離標準輸入，避免並行轉檔修改終端機回顯。若舊版本執行後打字看不到，輸入 `stty sane` 並按 Enter 可恢復，不必退出 iTerm2。

- 大量高解析度照片或影片需要較長處理時間及暫存空間。
- 預計輸出的 MP4 已存在時，跳過該素材目錄並記錄於終端機及 log，不覆寫。適用於預設檔名與自訂 `--output`；批次模式只處理尚未有輸出影片的子目錄，全部已存在時正常結束。
- 有子目錄時，每個第一層子目錄分別輸出影片，只讀取該子目錄直接包含的素材，不再向下遞迴。
