# CLAUDE.md

## プロジェクト概要

体重・血圧を中心とした個人健康管理リポジトリ。
脂質異常症・肥満傾向の改善を目的とし、「短期的に痩せること」ではなく
**再現できる生活習慣を作ること**を最優先とする。

---

## 目標（詳細は docs/goal.md 参照）

| フェーズ | 目標 | 基準値 |
|---|---|---|
| 開始時 | 現状把握 | 体重 93.6kg / BMI 33.5 |
| 第1目標 | 90kg台脱却 | 88.9kg以下（5%減） |
| 第2目標 | 中期改善 | 体重 82kg台・週5日以上歩行 |
| 最終目標 | 生活習慣確立 | 主治医と連携しながら脂質検査値を改善 |

---

## ファイル構成

```
health-project/
├── docs/
│   ├── baseline.md          # 初期測定値・ベースライン
│   ├── goal.md              # 目標設定
│   └── rules.md             # 運用ルール（完璧を目指さない）
├── logs/
│   ├── daily/
│   │   ├── weight.csv       # 日次：体重・体脂肪率
│   │   └── blood_pressure.csv  # 朝夜：血圧・脈拍・メモ
│   ├── lifestyle/
│   │   ├── meals.md         # 食事記録（ざっくりでOK）
│   │   └── exercise.md      # 運動記録
│   └── reviews/
│       └── weekly_review.md # 週次振り返り
├── scripts/
│   ├── analyze_health.py    # メイン分析（血圧リスク・相関・パターン検出）
│   ├── plot_weight.py       # 体重グラフ生成
│   ├── plot_blood_pressure.py  # 血圧グラフ生成
│   └── update_readme.py     # README自動更新
├── reports/
│   ├── health_analysis.md   # 自動生成：分析サマリー
│   ├── weight.png           # 自動生成：体重グラフ
│   └── blood_pressure.png   # 自動生成：血圧グラフ
├── .github/workflows/
│   └── health-report.yml    # GitHub Actions：push時に自動レポート生成
├── requirements.txt
└── CLAUDE.md                # このファイル
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
date,time,systolic,diastolic,pulse,memo
YYYY-MM-DD,morning/night,XXX,XX,XX,メモ
```
- `time`: `morning`（起床後）または `night`（就寝前）
- `systolic`: 収縮期血圧（mmHg）
- `diastolic`: 拡張期血圧（mmHg）
- `pulse`: 脈拍（bpm）
- `memo`: 任意メモ（空白OK）

---

## 運用ルール（重要：docs/rules.md より）

- 体重は**1日1回**記録する（血圧は任意）
- 体重の良し悪しは**7日平均**で判断する（日々の増減は気にしない）
- 3日サボってもOK、再開すればOK
- 完璧な食事記録・カロリー計算は**不要**
- 増えていたら食事見直し／停滞したら運動増加／減っていたら維持

---

## 血圧の判定基準

| 状態 | 収縮期 | 拡張期 |
|---|---|---|
| 正常 | 130未満 | 85未満 |
| やや高め（注意） | 130〜139 | 85〜89 |
| 高め（受診検討） | 140以上 | 90以上 |

- **朝の血圧を優先**して評価する（心血管リスク評価に重要）
- 脈拍100超は頻脈の目安として記録・確認する

---

## GitHub Actions 自動化

`main` ブランチへの push 時に以下が自動実行される：

1. `plot_weight.py` → `reports/weight.png` 生成
2. `plot_blood_pressure.py` → `reports/blood_pressure.png` 生成
3. `analyze_health.py` → `reports/health_analysis.md` 生成
4. `update_readme.py` → `README.md` 更新
5. 変更を自動コミット＆プッシュ（`[skip ci]` 付き）

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
「体脂肪率の推移もレポートに加えて」
「脈拍の異常値（100超）があった日を抽出して」
```

### スクリプト改善
```
「脈拍の異常検出ロジックをanalyze_health.pyに追加して」
「朝夜別の血圧分析を追加して」
「体脂肪率の分析をanalyze_health.pyとレポートに加えて」
```

### 週次レビュー・計画
```
「今週のデータを要約してweekly_review.mdを作成して」
「来週の運動プログラムをexercise.mdに提案して」
「目標体重88.9kgまでの進捗率を計算して」
```

### Git操作
```
「変更をすべてステージしてコミットしてpushして」
「今日の記録をまとめてコミットして」
```

---

## 注意事項

- 医療的な判断は必ず主治医に相談すること
- このリポジトリの分析はあくまで**参考情報**であり、診断ではない
- 脂質異常症の管理は食事・運動に加え、定期的な血液検査で確認する
