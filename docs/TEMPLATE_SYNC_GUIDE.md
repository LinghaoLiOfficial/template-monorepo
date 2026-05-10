# 模板上游同步指南（Template Upstream Sync Guide）

## 1. 目标（Goal）

本指南定义“模板仓库（Template Repo）”与“消费仓库（Consumer Repo）”之间的可重复同步流程，避免项目初始化后与上游改进断连。

## 2. 核心原则（Core Principles）

- 模板优先（Template-first）：工程基座改进优先沉淀到模板仓库。
- 分区同步（Zoned Sync）：按 `auto_apply / merge_apply / manual_only` 处理。
- 先检查后应用（Check before apply）：先看影响，再打补丁。
- 同步必验证（Verify after sync）：同步完成后必须跑全量质量门禁。

## 3. 关键文件（Key Files）

- `.template-sync-manifest.yaml`：同步分区策略。
- `scripts/template/release_template.sh`：模板发布脚本。
- `scripts/template/build_patch_bundle.sh`：模板差异补丁生成。
- `scripts/template/check_sync_impact.py`：同步影响分析。
- `scripts/sync_template.sh`：消费仓库同步入口。
- `scripts/post_sync_verify.sh`：同步后验证入口。

## 4. 模板发布流程（Template Release Flow）

1. 在模板仓库整理并合并改进。
2. 运行：

```bash
scripts/template/release_template.sh v1.0.0
```

3. 推送 tag：

```bash
git push origin template-v1.0.0
```

## 5. 消费仓库同步流程（Consumer Sync Flow）

1. 创建同步分支：

```bash
git checkout -b chore/sync-template-v1.0.0
```

2. 先预演（dry-run）：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0 --dry-run
```

3. 确认后执行正式同步：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0
```

若希望在存在 `unknown` 文件时直接阻断（推荐用于严格团队流程）：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0 --fail-on-unknown
```

若希望产出机器可读报告（JSON）用于 CI 归档与审计：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0 --dry-run --report-file artifacts/sync-report.json
```

若只需要计数摘要报告（更适合 CI 精简日志）：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0 --dry-run --report-file artifacts/sync-summary.json --report-format summary
```

若希望同时在终端打印报告（便于 CI 日志查看）：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0 --dry-run --report-file artifacts/sync-report.json --report-stdout
```

若希望所有产物统一落到同一目录：

```bash
scripts/sync_template.sh --from template-v0.9.0 --to template-v1.0.0 --dry-run --artifact-dir artifacts/sync-run
```

4. 处理冲突并确认 `manual_only` 文件不被误覆盖。
5. 执行验证：

```bash
scripts/post_sync_verify.sh
```

6. 提交并发起 PR。

## 6. 冲突处理建议（Conflict Handling）

- `auto_apply` 冲突：优先保留上游模板实现。
- `merge_apply` 冲突：按项目上下文进行三方合并。
- `manual_only` 冲突：必须人工审查，不允许自动覆盖。

## 7. 冲突决策矩阵（Conflict Decision Matrix）

| 场景 | 推荐动作 | 结果要求 |
|---|---|---|
| `auto_apply` 文件冲突 | 以模板版本为主，项目侧仅补回必要环境差异 | 重新跑全量验证 |
| `merge_apply` 文件冲突 | 逐段三方合并，保留项目业务配置与模板基础能力 | 关键配置有变更说明 |
| `manual_only` 文件变更 | 不自动套用，改为人工对照迁移 | PR 中给出迁移清单 |
| 出现 `unknown` 文件 | 更新 `.template-sync-manifest.yaml` 分区策略后再同步 | 不允许带未知策略合并 |

## 8. 版本策略（Versioning Policy）

- `template-vMAJOR.MINOR.PATCH`
- MAJOR：破坏性变更（Breaking Change）
- MINOR：向后兼容新增（Backward-Compatible Feature）
- PATCH：缺陷修复（Bug Fix）

## 9. 发布节奏（Release Cadence）

- 建议节奏：每月 1 次 MINOR 发布，每周按需 PATCH 发布。
- 发布入口：固定由模板维护者在 `main` 分支打 tag。
- 发布产物：
  - `docs/template-releases/template-vX.Y.Z.md`
  - `artifacts/template-patches/*`
- 消费仓库 SLA：建议在 2 个发布周期内完成升级，避免漂移扩大。

## 10. CI 接入建议（CI Integration）

建议在 CI 增加“模板同步守卫（template-sync-guard）”：

- 校验 manifest 严格合法（`--validate-only`）。
- 校验同步脚本具备 `--dry-run` 路径。
- 在模板自身仓库，使用 `HEAD~1 -> HEAD` 做 `--summary-only --strict` 分区检查。
- 同步报告建议开启 `--report-stdout`，便于日志和 artifact 同时追踪。

参考工作流：`.github/workflows/template-sync-ci.yml`。

## 11. PR 检查建议（PR Checklist）

模板同步相关 PR 建议强制包含：

- 本次 `from/to` 模板版本。
- `manual_only` 是否有人工迁移。
- `post_sync_verify` 是否通过。
- 风险与回滚方式。
