
## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- 單表 Purview 稽核、PII 風險、血緣分析、單表欄位合規 → invoke purview-audit
- 批次 PII 掃描、哪些表有敏感資料、schema PII 風險矩陣 → invoke pii-scan
- 變更前影響分析、下游依賴、誰在用這張表、改 schema 前 → invoke data-impact
- 過時/閒置資料表、很久沒更新、資料新鮮度檢查、廢棄表清理 → invoke stale-tables
- 欄位命名規範、欄位合規（整張表自動抓 schema）、驗證欄位名稱 → invoke glossary-check
