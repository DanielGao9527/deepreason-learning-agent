# 二叉树的一般定义

来源：OpenDSA，Binary Trees / Definitions and Properties
原文页面：https://opendsa.cs.vt.edu/ODSA/Books/Everything/html/BinaryTree.html
许可：https://opendsa.cs.vt.edu/home/license （MIT）
整理日期：2026-09-29。本文件是根据来源写的中文提要，不是原文翻译全文。

二叉树可以为空。非空二叉树由一个根结点和两棵彼此不重叠的子树组成，分别叫左子树、右子树；两棵子树本身也都是二叉树。因此，一个结点最多有两个非空孩子，左、右位置有区别。

这个一般定义没有规定结点的键必须按大小排列，也没有规定树必须平衡。二叉搜索树是在二叉树上另加搜索顺序约束的特例。
