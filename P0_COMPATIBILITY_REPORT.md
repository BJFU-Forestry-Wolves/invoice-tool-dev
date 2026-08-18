# P0 OCR 兼容性验证记录

## 已锁定候选矩阵

- Windows 10/11 x64
- Python 3.11.15
- PaddlePaddle CPU 3.2.0
- PaddleOCR 3.7.0
- PaddleX 3.7.2（`ocr-core`）
- PP-OCRv6 medium 检测与识别模型
- PyInstaller 6.22.2，`onedir`

## 本机验证结果

- PaddlePaddle CPU 自检通过。
- JPG、JPEG、PNG、BMP、PDF 共 10 个冒烟样本全部成功。
- 最终 Python 基准总耗时 36.879 秒，其中产线初始化 3.370 秒、10 个样本累计纯推理 33.264 秒，平均 3.326 秒。
- Python 进程峰值工作集 2,849,681,408 字节（约 2,717.67 MiB）。
- BMP 单文件约 6.1–6.5 秒；PDF 单文件约 1.8–2.6 秒。
- 三套模型根文件合计 146,031,223 字节，不含下载缓存元数据。
- PyInstaller 目录包共 1,698 个文件、588,722,750 字节（约 561.45 MiB）。
- 打包 EXE 在禁用模型源检查、启用 Hugging Face 离线模式、HTTP/HTTPS 指向不可用代理时成功识别 JPG 样本，退出码 0；推理约 4.3 秒。

## 已发现并固化的约束

1. Paddle Inference 3.2.0 在 Windows 上不能从含中文字符的模型路径打开静态模型文件。模型必须先复制到 `%LOCALAPPDATA%\\InvoiceAttachmentTool\\models` 之类的 ASCII 路径，再初始化 OCR。
2. PyInstaller 不能对 Paddle 使用无差别 `collect_all()`；这会收集训练、分布式、TensorRT 和 JIT SOT 路径，并导致依赖扫描子进程崩溃。
3. PaddleX OCR 产线需要携带 `paddlex` 及 `ocr-core` 依赖的 `.dist-info`，否则冻结程序会误报 OCR extra 未安装。
4. PaddleX 顶层初始化依赖模型注册清单，不能整体排除 `paddlex.modules` 或 `paddlex.repo_apis`。
5. 发布程序必须设置 `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=1`，并在启动 OCR 前完成模型哈希校验，禁止静默联网下载。

## P0 状态

PP-OCRv6 Python 与 PyInstaller onedir 主路径已在本机通过。仍需在干净、无 Python、物理断网的 Windows 测试机复验后，才能把 P0 标记为最终完成并进入 P1。
