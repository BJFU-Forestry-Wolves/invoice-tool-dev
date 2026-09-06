# 第三方软件与模型声明

本项目自身代码采用 MIT License。运行和构建依赖仍受各自许可证约束：

| 组件 | 用途 | 许可证/上游 |
|---|---|---|
| PaddlePaddle | OCR 推理 | Apache-2.0，<https://github.com/PaddlePaddle/Paddle> |
| PaddleOCR / PP-OCRv6 模型 | 文字检测与识别 | Apache-2.0，<https://github.com/PaddlePaddle/PaddleOCR> |
| PaddleX | OCR 推理管线 | Apache-2.0，<https://github.com/PaddlePaddle/PaddleX> |
| Pillow | 图片处理 | HPND，<https://python-pillow.org/> |
| openpyxl | Excel 读写 | MIT，<https://openpyxl.readthedocs.io/> |
| PyInstaller | Windows 打包 | GPL-2.0-or-later with bootloader exception，<https://pyinstaller.org/> |

发布模型包时必须保持模型名称、版本和来源说明，不得将第三方模型标记为本项目原创。
完整的传递依赖许可应在正式发布前由发布者根据构建环境再次生成并核对。
