# K-means：距离最小化的迭代聚类

非监督学习的判据很简单：看输入数据有没有标签。有标签是有监督学习，没标签就是无监督学习。聚类是无监督学习里最常用的一类，而 k-Means 是其中门槛最低、落地最广的算法。

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/ml_kmeans_problem.png" width="72%" alt="K-means 要解决的问题" />
  <p>图 1：肉眼能看出左边的点分成四群，任务就是让程序自动找出这些点群</p>
</div>

## 1. 算法流程

下图给出一个有 5 个点 A、B、C、D、E 的例子，灰色点是种子点（用来找点群的点）。这里有两个种子点，所以 K=2。

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/ml_kmeans_steps.jpeg" width="60%" alt="K-means 迭代过程" />
  <p>图 2：聚类的四步迭代——分配、移动种子点、再分配、直到种子点不再移动</p>
</div>

K-Means 的算法步骤：

1. 随机在图中取 K（这里 K=2）个种子点；
2. 对图中所有点求到这 K 个种子点的距离。若点 \(P_i\) 离种子点 \(S_i\) 最近，则 \(P_i\) 属于 \(S_i\) 点群（图中 A、B 属于上面的种子点，C、D、E 属于中部的种子点）；
3. 移动种子点到属于它的「点群」的中心（见图上的第三步）；
4. 重复第 2、3 步，直到种子点不再移动（图中第四步时，上面的种子点聚合了 A、B、C，下面的种子点聚合了 D、E）。

整个算法的目标函数是「各点到所属中心的距离之和」，所以它天然倾向于产生大小接近、形状接近球形的簇。

## 2. 求点群中心的几种距离

计算中心点最简单的方式是取各个点 X/Y 坐标的平均值。除此之外，常用的三个公式决定了「中心」的定义：

**Minikowski Distance** —— \(\lambda\) 可以随意取值，可以是负数、正数或无穷大：

$$
D(x, y) = \left(\sum_{i=1}^{n}\left|x_i - y_i\right|^{\lambda}\right)^{1/\lambda}
$$

**Euclidean Distance** —— 即第一个公式 \(\lambda = 2\) 的情况：

$$
D(x, y) = \sqrt{\sum_{i=1}^{n}\left(x_i - y_i\right)^2}
$$

**CityBlock Distance** —— 即第一个公式 \(\lambda = 1\) 的情况：

$$
D(x, y) = \sum_{i=1}^{n}\left|x_i - y_i\right|
$$

三种距离下「中心点」的位置并不相同：

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/ml_kmeans_distance_centers.jpeg" width="80%" alt="三种距离对应的中心" />
  <p>图 3：同样的点集在三种距离度量下的中心位置（\(0<\lambda<1\) 的 Minkowski 呈星形，Euclidean 呈圆形，CityBlock 呈菱形）</p>
</div>

这张图很直观地说明了为什么「距离度量决定了簇的形状」：距离的等高线是圆的，簇就偏圆；等高线是菱形的，簇就偏向菱形分布。

## 3. 两个与初始值有关的缺陷

K-Means 最重大的两个缺陷都和初始值有关。

**K 值难以估计**。K 是事先给定的，而很多时候并不知道数据集应该分成多少个类别才最合适。ISODATA 算法通过类的自动合并与分裂，得到较为合理的类型数目 K。

**随机种子点太关键**。不同的随机种子点会得到完全不同的结果。K-Means++ 可以用来有效选择初始点，步骤是：

1. 先从数据库随机挑一个随机点当「种子点」；
2. 对每个点计算它和最近一个「种子点」的距离 \(D(x)\) 并存入数组，再把这些距离累加得到 \(\mathrm{Sum}(D(x))\)；
3. 取一个能落在 \(\mathrm{Sum}(D(x))\) 中的随机值 \(\mathrm{Random}\)，然后不断做 \(\mathrm{Random} \mathrel{-}= D(x)\)，直到其 \(\le 0\)，此时的点就是下一个「种子点」；
4. 重复第 2、3 步，直到 K 个种子点全部选出；
5. 执行 k-Means 算法。

第 3 步的实质是**按距离加权抽样**：离已有种子点越远的点，被选中的概率越大。这样初始中心天然分散，避免了「多个中心挤在同一团」的退化情形。

## 写在最后

k-Means 用的是硬分配——每个点只属于一个簇。若希望得到「属于每个簇的概率」，就需要把高斯分布与 EM 算法引进来，这就是下一篇的高斯混合模型。
