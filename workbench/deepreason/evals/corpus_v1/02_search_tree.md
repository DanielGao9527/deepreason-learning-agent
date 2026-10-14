# 二叉搜索树：顺序与高度

来源：OpenDSA, Binary Search Trees / Balanced Trees。原文页面：https://opendsa.cs.vt.edu/OpenDSA/Books/Catalog/html/BST.html
补充页面：https://opendsa.cs.vt.edu/ODSA/Books/nyu/csci-ua102/spring-2021/section_5/html/BalancedTree.html
整理方式：本项目为中文学习演示独立撰写的简短提要，不是 OpenDSA 原文复制。

二叉搜索树按键的顺序组织节点。查找和插入的代价与树高有关：保持平衡时，树高随节点数按对数增长；如果插入顺序造成严重倾斜，普通二叉搜索树可能退化为链表形状，操作代价接近线性。

“二叉搜索树”与“保证平衡的搜索树”不是同一个性能承诺。比较搜索树和哈希表时，先确认是否有平衡机制，以及任务是否需要有序遍历或范围查找。
