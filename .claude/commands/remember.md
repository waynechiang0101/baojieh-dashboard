把這次 session 的重要決定寫進 CLAUDE.md，然後 git commit + push。

格式：在 CLAUDE.md 最後面加一個 section：

```
## Session 記錄 YYYY-MM-DD（Claude Code）
- [決定1]
- [決定2]
- [pitfall 或注意事項]
```

寫完之後執行：
```bash
cd /Users/wayne/Downloads/fmcg-v4-1
git add CLAUDE.md
git commit -m "記錄：$ARGUMENTS"
git push
```

如果沒有給 $ARGUMENTS，commit message 用「記錄：Claude Code session」。
