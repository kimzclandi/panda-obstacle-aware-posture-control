# 第三方许可快照

采集日期：2026-10-04。对象仅为项目独立 `.venv` 的本地 distribution，不包含系统/ROS 的 PYTHONPATH 包，也不替项目源码选许可证。

- `inventory.json`：实际安装版本、上游 URL、原始许可元数据、归档清单和各文件 SHA-256。
- `notices/`：从实际安装包复制的 LICENSE / COPYING / NOTICE 文件，保留 site-packages 下相对路径。
- `notices/pybullet_data/franka_panda/LICENSE.txt`：本项目使用 Panda URDF/mesh 资产的 Apache-2.0 许可；区别于 PyBullet 主库 Zlib。

一些 wheel 附带其他组件或未用资产，归档它们的许可不表示项目使用了所有组件。许可摘要和用途见上一级 `attribution.md`；实际安装新增依赖后须更新快照。此目录只保存文档，不重新分发包代码或模型。
