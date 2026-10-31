# Windowsオフラインpytestの環境診断（2026-10-31）

## 判定

既知の54失敗・9エラーのうち、40失敗はWindows PowerShellのモジュール検索環境、9エラーはOpenSSLのPATH不足に分類した。アプリ実装・ACL検査・候補Plan検査は変更していない。残る14失敗はPOSIX API・symlink権限の制約であり、Windows全体pytestをPASSとは扱わない。

最初の再現はmain `7e7fa78e5ff34a998f1d1530c1fafe8ce82cf2b8`、Python 3.14.9 / uv 0.13.5 / locked依存で実施した。

| 対象 | 既存結果 | 分類・確認 |
| --- | ---: | --- |
| `test_candidate_artifact_snapshot.py` | 9失敗 | `os.mkfifo`、`os.O_NOFOLLOW`、`CandidateSnapshotPlatformUnsupportedHOLD`。POSIX専用の安全条件を維持 |
| `test_candidate_offline_controller.py` | 5失敗 | `os.O_NOFOLLOW`未提供・symlink作成権限。Linuxで検証する |
| `test_p4_bootstrap_diagnostics.py` | 32失敗 | `Get-Acl`のSecurityモジュール自動読込み失敗 |
| `test_p4_bootstrap_stages.py` | 8失敗 | 同じ診断ディレクトリACL検査で停止 |
| `test_plan_evidence.py` | 9エラー | `openssl`未検出。Git同梱の既存OpenSSLを子プロセスPATHへ追加 |

## ACL障害の根拠

機密を含まない新規ディレクトリに、既存`bootstrap_diagnostics.windows_private()`と同じACLスクリプトを実行した。継承環境では`CouldNotAutoloadMatchingModule`となり、明示Importの診断は`FormatXmlUpdateException`、`System.Security.AccessControl.ObjectSecurity`の`AuditToString`等の型定義重複だった。

同じPythonプロセスからの比較では、継承環境はFAIL、環境辞書から名前を大小文字を区別せず比較して`PSModulePath`を除去した子プロセスはPASS、Windows PowerShell標準Modulesだけを指定した子プロセスもPASSだった。環境変数名は実際には`PSMODULEPATH`で受け取られた。通常のPython辞書に対する`pop('PSModulePath')`はそのキーを除去できない。外側PowerShellの環境変更だけを根拠に、pytest子プロセスが隔離されたと判断しない。

確定できた原因は**継承されたモジュール検索環境に依存する型データの衝突**。個々のモジュールファイルの破損やOS全体の故障までは主張しない。モジュールの削除・再インストール、永続環境変数変更、ACLガードの迂回は不要だった。

対策後、診断・stages・Plan暗号化の3ファイルは**82 passed / 0 failed / 0 error**（47.94秒）。対策前の同じ3ファイルは40 failed / 42 passed。成功はMock/ローカルの診断・暗号化検証であり、AWS認証・実効IAM・本物のState/Planの受入成功ではない。

さらに、新しい隔離worktreeの統合HEAD `f437016a0b65e24e024cf97c0aeb4005f2e98567`で全体を確認した結果は**3,636 passed / 14 failed / 17 skipped / 57 deselected / 0 error**（167.56秒、exit 1）。失敗は上表のcandidate artifact 9件・offline controller 5件だけであり、40件のACL失敗と9件のOpenSSLエラーは再発しなかった。Linuxの同HEADでは既存CIの3,665 passed / 2 skipped / 57 deselectedを再利用する。新しいskip追加や期待値変更はない。

## 再現コマンド

`backend/`で`uv sync --locked`を完了した後、以下を実行する。これはオフラインテスト専用の一時的な子環境であり、AWS運用・Terraform実行用の環境には流用しない。OpenSSLは今回の端末に存在したGit同梱版を使用する。別端末では確認済みの実パスに合わせる。

```powershell
@'
import os
import subprocess
import sys

test_env = {
    key: value for key, value in os.environ.items()
    if key.casefold() != "psmodulepath"
}
test_env["PATH"] = r"C:\Program Files\Git\usr\bin;" + test_env["PATH"]
result = subprocess.run(
    [
        sys.executable, "-m", "pytest", "-q",
        "tests/unit/test_p4_bootstrap_diagnostics.py",
        "tests/unit/test_p4_bootstrap_stages.py",
        "tests/unit/test_plan_evidence.py",
    ],
    env=test_env,
    check=False,
)
sys.exit(result.returncode)
'@ | uv run --locked python -
```

全体試験は上記のテストファイル3つの引数を`"-m", "not dynamodb and not aws_e2e"`に置き換える。既存の`dynamodb`/`aws_e2e`除外とネットワーク遮断fixtureを維持する。POSIX専用試験を新たにskipへ変更しない。Linux全体の真正CI結果は[Backend run 41173130999](https://github.com/yonegen0/ai_interview/actions/runs/41173130999)で確認する。

## 公式仕様

[MicrosoftのPSModulePath仕様](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath)は、PowerShellがこの環境変数でモジュールを探索し、Windows PowerShellとPowerShell 7で標準パスと起動時の構築方法が異なることを説明している。今回の原因判定は上記のローカル比較実験に基づく。
