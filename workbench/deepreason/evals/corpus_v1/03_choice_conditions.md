# 选择哈希表还是树：先说明任务条件

来源：OpenDSA, Search Chapter Introduction / Abstract Data Types。原文页面：https://opendsa.cs.vt.edu/ODSA/Books/eu_book/html/SearchIntro.html
补充页面：https://opendsa.cs.vt.edu/ODSA/Books/cnu/cpsc270/fall-2017/TR8-915_TR130-245/html/ADT.html
整理方式：本项目为中文学习演示独立撰写的简短提要，不是 OpenDSA 原文复制。

如果核心任务只是按键精确查找，哈希索引通常是值得考虑的方案。如果任务要求按键排序、顺序遍历或范围查询，树形索引往往更合适；普通哈希表不保留键的顺序。

“哈希表一定比搜索树快吗”没有脱离场景的统一答案。至少要区分精确查找与范围查询、平均表现与最坏情况、普通 BST 与平衡树，并考虑具体实现和数据分布。课程材料能支持的是这些取舍条件，不是对某个程序运行速度的实测结论。
