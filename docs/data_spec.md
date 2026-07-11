# データ仕様・参照情報

## ファイル構成

```
health-project/
├── app/                         # PWAアプリ（モバイル入力用）
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── manifest.json
├── docs/
│   ├── baseline.md              # 初期測定値・ベースライン
│   ├── goal.md                  # 目標設定
│   ├── rules.md                 # 運用ルール
│   ├── daily_template.md        # 日次入力フォーマットの説明
│   └── data_spec.md             # このファイル
├── logs/
│   ├── daily/
│   │   ├── input.md             # 日次入力ファイル
│   │   ├── weight.csv           # 日次：体重・体脂肪率
│   │   └── blood_pressure.csv   # 朝夜：血圧・脈拍・メモ
│   ├── lifestyle/
│   │   ├── meals.md             # 食事記録
│   │   └── exercise.md          # 運動記録
│   └── reviews/
│       ├── weekly_review.md     # 最新週次振り返り
│       └── archive/weekly/      # 過去の週次レビュー
├── scripts/
│   ├── analyze_health.py        # メイン分析（血圧リスク・相関・パターン検出）
│   ├── plot_weight.py           # 体重グラフ生成
│   ├── plot_blood_pressure.py   # 血圧グラフ生成
│   ├── generate_weekly_review.py # 週次レビュー自動生成
│   └── update_readme.py         # README自動更新
├── reports/
│   ├── health_analysis.md       # 自動生成：分析サマリー
│   ├── weight.png               # 自動生成：体重グラフ
│   └── blood_pressure.png       # 自動生成：血圧グラフ
├── .github/workflows/
│   ├── health-report.yml        # push時に自動レポート生成
│   └── weekly-review.yml        # 水曜夜血圧push時に週次レビュー生成
├── requirements.txt
└── CLAUDE.md
```

---

## CSVデータ仕様

### logs/daily/weight.csv
```
date,weight,bodyfat
YYYY-MM-DD,XX.X,XX.X
```
- `weight`: 体重（kg）
- `bodyfat`: 体脂肪率（%）、任意

### logs/daily/blood_pressure.csv
```
date,time,systolic1,diastolic1,pulse1,systolic2,diastolic2,pulse2,memo
YYYY-MM-DD,morning/night,XXX,XX,XX,XXX,XX,XX,メモ
```
- `time`: `morning`（起床後）または `night`（就寝前）
- `systolic1/2`: 収縮期血圧（mmHg）1回目・2回目
- `diastolic1/2`: 拡張期血圧（mmHg）1回目・2回目
- `pulse1/2`: 脈拍（bpm）1回目・2回目
- `memo`: 任意メモ。朝行には `cpap:on` または `cpap:off` を記入
- 1回計測の場合は systolic1=systolic2、diastolic1=diastolic2、pulse1=pulse2 に同じ値を入れる
- 血圧を測り忘れた日でもCPAPだけは記録できる。その場合 systolic1〜pulse2 は空欄にし、memoにcpap:on/offのみ記入する
  （例: `2026-07-11,morning,,,,,,,cpap:on`）

---

## GitHub Actions 自動化

### health-report.yml
`main` ブランチへの push 時に自動実行：
1. `plot_weight.py` → `reports/weight.png`
2. `plot_blood_pressure.py` → `reports/blood_pressure.png`
3. `analyze_health.py` → `reports/health_analysis.md`
4. `update_readme.py` → `README.md` 更新
5. 自動コミット＆プッシュ（`[skip ci]` 付き）

### weekly-review.yml
`logs/daily/blood_pressure.csv` への push 時（水曜夜血圧を検知）に自動実行：
- `generate_weekly_review.py` → `logs/reviews/weekly_review.md`
- `--force` オプションで強制実行も可能（workflow_dispatch）

---

## Claude Code への依頼例

### データ追加
```
「今日の体重XX.XkgをCSVに追記してコミットして」
「今朝の血圧 収縮期XXX 拡張期XX 脈拍XXをCSVに追記して」
```

### 分析・レポート
```
「今週の体重トレンドを7日平均で分析して」
「血圧の朝夜別の推移を比較して」
「脈拍の異常値（100超）があった日を抽出して」
```

### スクリプト改善
```
「脈拍の異常検出ロジックをanalyze_health.pyに追加して」
「体脂肪率の分析をanalyze_health.pyとレポートに加えて」
```

### 週次レビュー・計画
```
「今週のデータを要約してweekly_review.mdを作成して」
「目標体重88.9kgまでの進捗率を計算して」
```

---

## 注意事項

- 医療的な判断は必ず主治医に相談すること
- このリポジトリの分析はあくまで参考情報であり、診断ではない
- 脂質異常症の管理は食事・運動に加え、定期的な血液検査で確認する
