# TimesFM CPU 第三方来源

- Google Research `timesfm==2.0.2`（提供 `TimesFM_2p5_200M_torch`）：Apache-2.0。保留精确 wheel 的完整 [LICENSE](LICENSE.timesfm)，provision 也复制到 ignored 模型目录；该 wheel 没有单独 NOTICE。不复制或修改上游实现。
- 权重：[google/timesfm-2.5-200m-pytorch](https://huggingface.co/google/timesfm-2.5-200m-pytorch/tree/1d952420fba87f3c6dee4f240de0f1a0fbc790e3)，revision `1d952420fba87f3c6dee4f240de0f1a0fbc790e3`，模型卡声明 Apache-2.0；模型卡/config/权重及 LICENSE 的 SHA-256 进入本地 manifest。完整模型卡保留在 ignored 模型目录。
- PyTorch CPU：只安装 [官方 CPU wheel](https://download.pytorch.org/whl/cpu/torch/)，版本 `2.8.0+cpu`。各依赖保留各自分发包中的许可证，精确版本见 `requirements.lock`。

这些版本不会自动升级到 TimesFM 3.0，也不允许替换 checkpoint。Git 不包含权重或 wheels。
