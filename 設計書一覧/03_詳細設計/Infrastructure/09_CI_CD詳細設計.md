# CI/CD詳細設計

> 文書バージョン: 2.1\
> 更新日: 2026-09-11  
> 対象フェーズ: Backend実装・Terraform構築・実API接続  
> 情報源方針: 実装時は最新の公式ドキュメントを最優先で再確認する。


## 1. 現状
[Frontend GitHub Actions](../../../.github/workflows/frontend.yml)は実装済み。
Node.js 22、lint・型・テスト・本番／Storybook／Mockビルド・E2Eを実行する。
Backend・Terraform・公開を含む全体CI/CDは未確定。GitHub Actionsを第一候補とする。

## 2. Pipeline候補
Frontend lint/test → Backend lint/test → package build →
Terraform fmt/validate/plan → approval → apply → Frontend deploy。

## 3. 分離
Infrastructure applyとApplication build/packageの責務を分離する。

## 4. Secret
OpenAI Secret実値をTerraformへ渡さない。

## 5. 検証記録

過去の成功件数を現在の成功保証として扱わず、実行日と対象を記録する。
マスコットWebPの実寸法と512px期待値の不一致は既知のE2E問題。
テストを除外・期待値変更して成功扱いにせず、結果に明記する。
