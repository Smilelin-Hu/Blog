# 密钥、凭据与秘密管理：Vault、External Secrets 与轮换

28 讲身份与 RBAC（「谁能做什么」），本文补「工作负载拿什么去做」：训练与推理作业要取用对象存储 AK/SK、模型 API key、数据库口令、制品仓库拉取凭据与实验平台 token。这些凭据的存放、注入、轮换与泄漏响应，是多租户平台的先决条件——身份边界再严，一个明文躺在 Git 里的 AK 就能全部绕过。

## 1. 为什么单靠 K8s Secret 不够

- K8s Secret 默认只是 base64 编码而非加密，etcd 静态加密（EncryptionConfiguration）需显式开启；能读 etcd 或拿到节点权限即拿到全部 Secret。
- Secret 的 RBAC 边界粗：命名空间内 get secrets 一把抓，无法按 key 细分；list/watch 一次拉全量。
- 最大泄漏面不在集群而在 Git 与镜像：明文 commit、Dockerfile ARG 传入的 token、CI 日志回显。历史 commit 里的密钥即使删除文件也仍可检出，**泄漏即轮换，删文件不算处置**。

AI 工作负载凭据清单（盘点口径）：对象存储 AK/SK（数据集与 checkpoint）、模型 API key（合成数据/评测/judge）、数据库口令（标注平台/元数据）、registry 拉取凭据、HF/W&B 等 SaaS token、集群间联邦凭证。每类都要有 owner、存放位置、轮换周期与泄漏预案。

## 2. 外部秘密存储与三种注入模式

原则：**秘密只存一处（外部 secret store），集群内只有投影**。主流后端：HashiCorp Vault（自建，动态秘密能力强）、云 KMS/Secrets Manager（托管，与云 IAM 原生集成）。

| 注入模式 | 机制 | 轮换行为 | 适用 |
|---|---|---|---|
| External Secrets Operator（ESO） | CRD 声明 SecretStore + ExternalSecret，控制器周期同步为 K8s Secret | refreshInterval 到期重同步；应用需 reload/重启才生效 | 通用工作负载，与现有 env/volume 用法兼容 |
| Secrets Store CSI Driver | 以 CSI 卷把秘密挂载为文件，可选同步为 K8s Secret | 轮换轮询自动更新挂载文件；应用读文件即拿到新值 | 需要文件型凭据、免重启轮换 |
| SDK 直取 | 应用启动/运行时直接向 Vault/KMS 请求 | 天然短生命周期，lease 到期续租 | 有能力改造代码的核心服务 |

ESO 的代价是「秘密又落回 etcd」——它解决的是来源统一与 GitOps 友好，不是消灭 K8s Secret；对高敏凭据优先 CSI 挂载或 SDK 直取，并开启 etcd 静态加密兜底。

## 3. Vault 核心机制：认证、策略与动态秘密

- **认证**：Kubernetes auth method 用 Pod 的 ServiceAccount JWT 换取 Vault token，把 28 的工作负载身份直接映射为秘密访问身份，无需预分发静态凭据；CI 侧用 JWT/OIDC（keyless 思路同源）。
- **策略**：Vault policy 按路径最小授权（`secret/data/tenant-a/*` 只读），与 RBAC 一样是纯加法，定期做有效权限差异分析。
- **动态秘密**：数据库/云厂商引擎按需签发短生命周期凭据（如 1 小时 TTL 的数据库账号、临时云凭证），lease 到期自动吊销。相比「一把静态 AK 用三年」，泄漏窗口从年缩到小时，且每个作业可签发独立凭据——审计能精确到「哪个作业用了哪次签发」。
- 租约续租（renew）与吊销（revoke）要有监控：续租失败堆积意味着作业即将批量失去数据访问。

## 4. 轮换工程：重叠窗口与生效路径

轮换的难点不是「生成新值」，而是**新旧凭据的重叠窗口与消费侧生效**：

1. 双凭据重叠：先签发新凭据并注入，确认全部消费者切换后再吊销旧值；直接「先吊销后分发」会造成在途作业批量失败（训练作业读 checkpoint 中途 403 是典型事故）。
2. 生效路径分三档：读文件型（CSI 挂载）自动生效；env 注入型必须重启/reload——ESO 同步了新 Secret 不代表应用用上了，需要 rollout 联动或应用侧热加载。
3. 周期与触发：静态凭据按周期（常见 30–90 天）自动轮换；泄漏事件触发即时轮换。模型 API key 轮换要与网关侧吊销联动（主题三 16 篇第 14 节的凭证保护），否则旧 key 在网关仍可用。
4. 轮换演练进 27 的故障演练科目：验证重叠窗口、生效路径与回滚（新凭据有误时旧值仍可兜底）。

## 5. GitOps 边界与 CI 防线

- 明文秘密永不进 Git。GitOps 需要「秘密相关声明可入库」时用加密形态：Sealed Secrets（集群内私钥解密）、SOPS + age/KMS（文件级加密，Mozilla 系工具链），密文可评审、私钥不进仓库；ESO 路线则 Git 里只有 ExternalSecret 引用，值完全在外部存储。
- CI 防线：gitleaks/trufflehog 类扫描进 pre-commit 与 CI 双卡口；构建参数禁止 ARG 传密（会留在镜像层历史），用 BuildKit secret mount；CI 日志对 token 模式打码。
- 本机开发凭据放被 gitignore 的本地文件（如 `.env.local`），不入库、不写进文档。

## 6. 泄漏响应与验收

泄漏处置顺序：**先吊销/轮换，再溯源，最后复盘**——吊销止损优先于查清范围。溯源靠 Vault 审计日志 + K8s 审计（28 篇第 8 节）关联「谁在何时取过该秘密」，评估爆炸半径（该凭据能访问的数据/模型/租户）。复盘更新凭据清单与扫描规则。

验收清单：etcd 静态加密开启；Git 历史扫描零明文（含历史 commit）；凭据清单每类有 owner 与轮换周期；动态秘密覆盖数据库/云凭证；轮换演练通过（重叠窗口内零作业失败）；泄漏演练从告警到吊销的 MTTR 有记录。

## 写在最后

秘密管理把「凭据从哪来、怎么换、漏了怎么办」变成平台能力；下一层问题是这些能力所依赖的云资源本身如何声明式地创建与保持一致：[平台基础设施即代码](/source/AI-Infra/4-AI平台工程/38-平台基础设施即代码-Terraform-Crossplane-环境一致性)。