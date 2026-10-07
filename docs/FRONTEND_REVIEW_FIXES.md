# Frontendレビュー指摘の修正結果

[未コミット差分レビュー](FRONTEND_UNCOMMITTED_REVIEW_20261006.md)のF1〜F5を修正した。
既存の未コミット変更を保持し、コミット・配備は実施していない。

| 指摘 | 修正した挙動 | 主な変更先 |
|---|---|---|
| F1: 別利用者で401再送 | 要求開始時の利用者と認証世代を保持し、認証取得・応答・JSON読取の完了後に確認。同じ利用者の再ログインも旧処理と区別する。同じログイン内の401再確認は同じ本文とキーで1回だけ行う。 | `lib/api/client.ts`、`lib/auth/session.ts` |
| F2: 遅延応答で別利用者の保存を削除 | `useOperationScope`で保存先を固定。アンマウント・ログイン変更後の保存更新、Cache更新、遷移を止める。Query/Mutationが実際に実行される直前にも確認する。保護画面は認証世代の変更で再マウントする。 | `hooks/useOperationScope.ts`、認証境界、開始・回答・評価・管理・結果のhooks |
| F3: quota後に古い保存を読む | 書込失敗したキーでは最新memoryを優先。削除失敗時はmemoryに削除済み状態を保持し、古い永続レコードを復活させない。書込復旧後は通常の読取へ戻す。 | `lib/storage/recovery.ts` |
| F4: 古いCacheで誤った競合 | 画面への再入場時に必ず新しいGETを行い、その成功後に復旧データと比較。保存成功時に一覧Cacheを更新。管理者Cacheも利用者別キーにする。 | `features/admin/hooks/useQuestionManagement.ts` |
| F5: 旧要求が再実行される | 旧要求のfingerprint・応答・UUIDキーを保持し、`mock-user`のキーへ対応付ける。修正前に作られたv2 Storeも補完し、すでに存在する利用者付き記録は保持する。version1原本は変更しない。 | `mocks/store/index.ts` |

APIのPayload・保存形式・Idempotency-Key、既存Sessionの質問スナップショットは維持する。
画面離脱後に結果が返った未確定要求は元の保存先に残し、同じ利用者が同じキー・本文で再確認できる。

## 回帰テスト

[review-fixes.test.tsx](../frontend/tests/review-fixes.test.tsx)に23件を追加した。

- 別利用者／同じ利用者の再ログイン後に返る401、2回目の401による新しい認証の誤った無効化、遅延JSON読取を遮断する。
- 同じログイン内の401再確認では本文・キーを保持する。
- 開始・次問・回答・管理者保存の遅延応答で、未確定要求と他の利用者の下書き・Cache・現在の画面を保護する。
- Mutationが実行される前に利用者が変わった場合は送信しない。同じ利用者で再ログインした後も保護画面を操作できる。
- 書込だけが失敗するquota、既存保存なし／あり、削除失敗、書込復旧、保存先の利用者分離、Mockの版と要求記録を確認する。
- 古いCacheと新しい保存済みbaselineがある管理画面、保存成功後の再入場を確認する。
- version1の開始・回答・次問の成功済み要求を再実行せず返し、旧原本を保全する。移行済みv2の補完と既存記録の保持も確認する。

## 検証結果

| 検証 | 結果 |
|---|---|
| `npm run lint` | 成功 |
| `npm run typecheck` | 成功 |
| `npm run test:unit` | 14ファイル、203件成功（追加23件を含む） |
| `npm test -- --project storybook` | 44ファイル、373件成功 |
| 最終認証境界のStory追加確認 | 4件成功 |
| `npm run build` | 成功。login・admin・練習・結果を静的生成 |
| `npm run build:mock` | 成功 |
| Playwright E2E | 13件成功。新しいローカルサーバー、CI設定、再試行0回で実行 |
| `git diff --check -- frontend` | 成功 |

外部認証はstub、APIはfetch stub／MSW、E2EはMock静的成果物で検証した。
実Cognito・AWSへの接続、資源変更、再有効化、配備は実施していない。

旧レビューのGit管理外6ケースは修正前の不具合を記録した証跡であり、誤った挙動をassertする。
修正後の確認には通常suiteに入った23件の回帰テストを使用する。
