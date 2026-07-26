# launchagents — launchd 單元的版本控制副本

`~/Library/LaunchAgents/` 不在 git 裡，所以那邊被改壞不會有人發現。
2026-07-26 撞到兩次：

1. `task-executor` 的直譯器被從 laapenv 換成 homebrew python3.12
   → laapenv 才有 pydantic → **評分路由 canary 靜默關掉**
   （只留一行 WARNING「Scoring router import failed ... bridge disabled」）
2. `task-executor` 與 `aris-relay` 的 `<string>` 裡有裸 `&&`（應為 `&amp;&amp;`）
   → `plutil -lint` 紅。launchd 舊 job 還跑得動，但重新 bootstrap 會失敗。

規矩：
- 改 `~/Library/LaunchAgents/com.neuralis.*.plist` 後，`cp` 一份到這裡並 commit。
- 改完跑 `plutil -lint`。
- 換直譯器前先確認新的那支有沒有同樣的套件（`pydantic` 是這次的地雷）。

同步回去：`cp launchagents/com.neuralis.*.plist ~/Library/LaunchAgents/`
